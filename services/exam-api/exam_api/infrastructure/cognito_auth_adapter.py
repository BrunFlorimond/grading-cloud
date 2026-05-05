"""Cognito adapter implementing AuthServicePort."""

from __future__ import annotations

import secrets
import string
from typing import Any

import aiobotocore.session
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from exam_api.domain.errors import (
    DuplicateEmailError,
    InvalidCredentialsError,
    TeacherGroupAssignmentError,
    WeakPasswordError,
)
from exam_api.cognito_group_names import COGNITO_TEACHER_GROUP
from exam_api.ports.auth_service_port import AuthChallenge, AuthServicePort, AuthTokens


class CognitoAuthAdapter(AuthServicePort):
    """Implements AuthServicePort using AWS Cognito via aiobotocore."""

    def __init__(
        self,
        *,
        user_pool_id: str,
        client_id: str,
        session: aiobotocore.session.AioSession | None = None,
        client: Any | None = None,
    ) -> None:
        self._user_pool_id = user_pool_id
        self._client_id = client_id
        self._session = session or aiobotocore.session.get_session()
        # Injected low-level client for tests (sync Mock methods replaced by AsyncMock in tests).
        self._injected_client = client

    async def register_teacher(
        self, *, email: str, password: str, full_name: str
    ) -> str:
        if self._injected_client is not None:
            return await self._register_teacher_with_client(
                self._injected_client,
                email=email,
                password=password,
                full_name=full_name,
            )
        async with self._session.create_client("cognito-idp") as client:
            return await self._register_teacher_with_client(
                client,
                email=email,
                password=password,
                full_name=full_name,
            )

    async def _register_teacher_with_client(
        self,
        client: Any,
        *,
        email: str,
        password: str,
        full_name: str,
    ) -> str:
        # User pool has self-service SignUp disabled (see infra AuthStack). Provision
        # teachers with AdminCreateUser + permanent password, same idea as student invite.
        temporary_password = self._generate_internal_temporary_password()
        try:
            create_response = await client.admin_create_user(
                UserPoolId=self._user_pool_id,
                Username=email,
                TemporaryPassword=temporary_password,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": full_name},
                ],
            )
        except ClientError as err:
            error_code = self._extract_error_code(err)
            if error_code == "UsernameExistsException":
                raise DuplicateEmailError(
                    "A teacher account already exists for this email."
                ) from err
            raise

        try:
            await client.admin_set_user_password(
                UserPoolId=self._user_pool_id,
                Username=email,
                Password=password,
                Permanent=True,
            )
        except ClientError as err:
            error_code = self._extract_error_code(err)
            if error_code == "InvalidPasswordException":
                await self._admin_delete_user_best_effort(client, email)
                message = err.response.get("Error", {}).get(
                    "Message", "Password does not meet the required policy."
                )
                raise WeakPasswordError(message) from err
            raise

        try:
            await client.admin_add_user_to_group(
                UserPoolId=self._user_pool_id,
                Username=email,
                GroupName=COGNITO_TEACHER_GROUP,
            )
        except ClientError as err:
            await self._admin_delete_user_best_effort(client, email)
            raise TeacherGroupAssignmentError(
                "Could not assign the new teacher to the teachers group."
            ) from err
        try:
            user_payload = create_response.get("User", {})
            return self._extract_user_sub(user_payload, email)
        except RuntimeError as err:
            await self._admin_delete_user_best_effort(client, email)
            raise TeacherGroupAssignmentError(
                "Could not read the new teacher identifier from Cognito."
            ) from err

    @staticmethod
    def _extract_user_sub(user_payload: dict[str, Any], username: str) -> str:
        attributes = user_payload.get("UserAttributes") or user_payload.get(
            "Attributes", []
        )
        if not isinstance(attributes, list):
            raise RuntimeError(
                f"Cognito response for {username} does not contain valid attributes."
            )
        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue
            if attribute.get("Name") != "sub":
                continue
            value = attribute.get("Value")
            if isinstance(value, str) and value:
                return value
        raise RuntimeError(f"Missing Cognito sub for user {username}.")

    @staticmethod
    def _generate_internal_temporary_password(length: int = 20) -> str:
        """Random temporary password satisfying typical Cognito complexity (mixed classes)."""
        if length < 8:
            raise ValueError("temporary password length must be at least 8")
        rng = secrets.SystemRandom()
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        symbol_alphabet = "!@#$%^&*()-_=+"
        required: list[str] = [
            rng.choice(string.ascii_uppercase),
            rng.choice(string.ascii_lowercase),
            rng.choice(string.digits),
            rng.choice(symbol_alphabet),
        ]
        remaining = length - len(required)
        chars = required + [rng.choice(alphabet) for _ in range(remaining)]
        rng.shuffle(chars)
        return "".join(chars)

    async def _admin_delete_user_best_effort(self, client: Any, username: str) -> None:
        """Remove a user after a failed provisioning step; ignores delete errors."""
        try:
            await client.admin_delete_user(
                UserPoolId=self._user_pool_id,
                Username=username,
            )
        except ClientError:
            pass

    async def login_teacher(self, *, email: str, password: str) -> AuthTokens:
        if self._injected_client is not None:
            return await self._login_teacher_with_client(
                self._injected_client,
                email=email,
                password=password,
            )
        async with self._session.create_client("cognito-idp") as client:
            return await self._login_teacher_with_client(
                client,
                email=email,
                password=password,
            )

    async def _login_teacher_with_client(
        self,
        client: Any,
        *,
        email: str,
        password: str,
    ) -> AuthTokens:
        try:
            response = await client.initiate_auth(
                ClientId=self._client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
            )
        except ClientError as err:
            error_code = self._extract_error_code(err)
            if error_code in {"NotAuthorizedException", "UserNotFoundException"}:
                raise InvalidCredentialsError("Invalid email or password.") from err
            raise

        auth_result = response.get("AuthenticationResult", {})
        return self._auth_tokens_from_result(auth_result)

    async def login_student(
        self, *, email: str, password: str
    ) -> AuthTokens | AuthChallenge:
        if self._injected_client is not None:
            return await self._login_student_with_client(
                self._injected_client,
                email=email,
                password=password,
            )
        async with self._session.create_client("cognito-idp") as client:
            return await self._login_student_with_client(
                client,
                email=email,
                password=password,
            )

    async def _login_student_with_client(
        self,
        client: Any,
        *,
        email: str,
        password: str,
    ) -> AuthTokens | AuthChallenge:
        try:
            response = await client.initiate_auth(
                ClientId=self._client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
            )
        except ClientError as err:
            error_code = self._extract_error_code(err)
            if error_code in {"NotAuthorizedException", "UserNotFoundException"}:
                raise InvalidCredentialsError("Invalid email or password.") from err
            raise

        challenge_name = response.get("ChallengeName")
        if challenge_name == "NEW_PASSWORD_REQUIRED":
            session = response.get("Session")
            if not isinstance(session, str):
                raise InvalidCredentialsError(
                    "Authentication response is missing challenge session."
                )
            return AuthChallenge(challenge_name=challenge_name, session=session)

        if challenge_name:
            raise InvalidCredentialsError(
                "Additional authentication steps are required for this account."
            )

        auth_result = response.get("AuthenticationResult", {})
        return self._auth_tokens_from_result(auth_result)

    async def respond_to_new_password_challenge(
        self, *, email: str, session: str, new_password: str
    ) -> AuthTokens:
        if self._injected_client is not None:
            return await self._respond_to_new_password_with_client(
                self._injected_client,
                email=email,
                session=session,
                new_password=new_password,
            )
        async with self._session.create_client("cognito-idp") as client:
            return await self._respond_to_new_password_with_client(
                client,
                email=email,
                session=session,
                new_password=new_password,
            )

    async def _respond_to_new_password_with_client(
        self,
        client: Any,
        *,
        email: str,
        session: str,
        new_password: str,
    ) -> AuthTokens:
        try:
            response = await client.respond_to_auth_challenge(
                ClientId=self._client_id,
                ChallengeName="NEW_PASSWORD_REQUIRED",
                Session=session,
                ChallengeResponses={
                    "USERNAME": email,
                    "NEW_PASSWORD": new_password,
                },
            )
        except ClientError as err:
            error_code = self._extract_error_code(err)
            if error_code == "InvalidPasswordException":
                message = err.response.get("Error", {}).get(
                    "Message", "Password does not meet the required policy."
                )
                raise WeakPasswordError(message) from err
            if error_code in {"NotAuthorizedException", "UserNotFoundException"}:
                raise InvalidCredentialsError("Invalid email or password.") from err
            raise

        auth_result = response.get("AuthenticationResult", {})
        return self._auth_tokens_from_result(auth_result)

    def _auth_tokens_from_result(self, auth_result: dict[str, Any]) -> AuthTokens:
        id_token = auth_result.get("IdToken")
        refresh_token = auth_result.get("RefreshToken")
        expires_in = auth_result.get("ExpiresIn")

        if (
            not isinstance(id_token, str)
            or not isinstance(refresh_token, str)
            or not isinstance(expires_in, int)
        ):
            raise InvalidCredentialsError(
                "Authentication response is missing required tokens."
            )

        return AuthTokens(
            id_token=id_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    @staticmethod
    def _extract_error_code(err: ClientError) -> str:
        return str(err.response.get("Error", {}).get("Code", ""))
