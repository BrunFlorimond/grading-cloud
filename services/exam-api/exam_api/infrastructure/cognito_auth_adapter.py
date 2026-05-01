"""Cognito adapter implementing AuthServicePort."""

from __future__ import annotations

from typing import Any

# TODO(#59): replace boto3 with aiobotocore once migration is complete.
# WARNING: boto3 and aiobotocore clients cannot share the same event loop.
# Replace ALL boto3 clients in this adapter atomically.
import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from exam_api.domain.errors import (
    DuplicateEmailError,
    InvalidCredentialsError,
    WeakPasswordError,
)
from exam_api.ports.auth_service_port import AuthServicePort, AuthTokens


class CognitoAuthAdapter(AuthServicePort):
    """Implements AuthServicePort using AWS Cognito via boto3.

    TODO(#59): migrate all methods to aiobotocore to remove asyncio.to_thread wrapping.
    Replace boto3.client("cognito-idp") with:
        session = aiobotocore.session.get_session()
        async with session.create_client("cognito-idp") as client:
            ...
    """

    def __init__(
        self,
        *,
        user_pool_id: str,
        client_id: str,
        client: Any | None = None,
    ) -> None:
        self._user_pool_id = user_pool_id
        self._client_id = client_id
        # TODO(#59): replace with aiobotocore async client (injected or created in __aenter__)
        self._client = client or boto3.client("cognito-idp")

    # TODO(#59): convert to native async def using aiobotocore — remove run_in_threadpool in auth_router
    async def register_teacher(self, *, email: str, password: str, full_name: str) -> str:
        # TODO(#59): replace all self._client.* calls with await self._client.*
        try:
            sign_up_response = self._client.sign_up(
                ClientId=self._client_id,
                Username=email,
                Password=password,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "name", "Value": full_name},
                ],
            )
        except ClientError as err:
            error_code = self._extract_error_code(err)
            if error_code == "UsernameExistsException":
                raise DuplicateEmailError(
                    "A teacher account already exists for this email."
                ) from err
            if error_code == "InvalidPasswordException":
                message = err.response.get("Error", {}).get(
                    "Message", "Password does not meet the required policy."
                )
                raise WeakPasswordError(message) from err
            raise

        self._client.admin_add_user_to_group(
            UserPoolId=self._user_pool_id,
            Username=email,
            GroupName="teachers",
        )
        self._client.admin_update_user_attributes(
            UserPoolId=self._user_pool_id,
            Username=email,
            UserAttributes=[{"Name": "custom:role", "Value": "teacher"}],
        )
        return str(sign_up_response["UserSub"])

    # TODO(#59): convert to native async def using aiobotocore — remove run_in_threadpool in auth_router
    async def login_teacher(self, *, email: str, password: str) -> AuthTokens:
        # TODO(#59): replace all self._client.* calls with await self._client.*
        try:
            response = self._client.initiate_auth(
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
