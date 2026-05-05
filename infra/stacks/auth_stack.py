from aws_cdk import CfnOutput, Fn, Stack
from aws_cdk import aws_apigatewayv2 as apigatewayv2
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ssm as ssm

from constructs import Construct

from stacks.constants import (
    COGNITO_ADMIN_GROUP,
    COGNITO_STUDENT_GROUP,
    COGNITO_TEACHER_GROUP,
)


class AuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # RBAC uses Cognito pool groups (teachers / students / admin) on the ID token.
        self.user_pool = user_pool = cognito.UserPool(
            self,
            "GradingUserPool",
            user_pool_name="grading-user-pool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=False),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=False,
            ),
        )

        cognito.CfnUserPoolGroup(
            self,
            "TeachersGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name=COGNITO_TEACHER_GROUP,
            description="Teacher users for grading platform.",
        )

        cognito.CfnUserPoolGroup(
            self,
            "StudentsGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name=COGNITO_STUDENT_GROUP,
            description="Student users for grading platform.",
        )

        cognito.CfnUserPoolGroup(
            self,
            "AdminGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name=COGNITO_ADMIN_GROUP,
            description="Administrators who may register new teachers via the API.",
        )

        self.user_pool_client = user_pool_client = user_pool.add_client(
            "GradingSpaClient",
            user_pool_client_name="grading-spa-client",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True,
            ),
            prevent_user_existence_errors=True,
        )

        http_api = apigatewayv2.CfnApi(
            self,
            "GradingHttpApi",
            name="grading-http-api",
            protocol_type="HTTP",
        )

        jwt_authorizer = apigatewayv2.CfnAuthorizer(
            self,
            "CognitoJwtAuthorizer",
            api_id=http_api.ref,
            authorizer_type="JWT",
            identity_source=["$request.header.Authorization"],
            name="cognito-jwt-authorizer",
            jwt_configuration=apigatewayv2.CfnAuthorizer.JWTConfigurationProperty(
                audience=[user_pool_client.user_pool_client_id],
                issuer=user_pool.user_pool_provider_url,
            ),
        )

        # HTTP proxy to a public echo URL so at least one route enforces the JWT authorizer
        # (no backend Lambda in this stack; replace with service integration later).
        auth_probe_integration = apigatewayv2.CfnIntegration(
            self,
            "AuthProbeHttpProxy",
            api_id=http_api.ref,
            integration_type="HTTP_PROXY",
            integration_method="GET",
            integration_uri="https://httpbin.org/get",
            payload_format_version="1.0",
        )

        apigatewayv2.CfnRoute(
            self,
            "AuthProbeRoute",
            api_id=http_api.ref,
            route_key="GET /auth-probe",
            authorization_type="JWT",
            authorizer_id=jwt_authorizer.ref,
            target=Fn.join("", ["integrations/", auth_probe_integration.ref]),
        )

        CfnOutput(
            self,
            "UserPoolId",
            value=user_pool.user_pool_id,
            export_name="GradingUserPoolId",
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            export_name="GradingUserPoolClientId",
        )

        CfnOutput(
            self,
            "CognitoIssuerUrl",
            value=user_pool.user_pool_provider_url,
            export_name="GradingCognitoIssuerUrl",
        )

        CfnOutput(
            self,
            "HttpApiId",
            value=http_api.ref,
            export_name="GradingHttpApiId",
        )

        CfnOutput(
            self,
            "HttpApiEndpoint",
            value=http_api.attr_api_endpoint,
            export_name="GradingHttpApiEndpoint",
        )

        CfnOutput(
            self,
            "HttpApiJwtAuthorizerId",
            value=jwt_authorizer.ref,
            export_name="GradingHttpApiJwtAuthorizerId",
        )

        ssm.StringParameter(
            self,
            "UserPoolIdParam",
            parameter_name="/grading/cognito/user-pool-id",
            string_value=user_pool.user_pool_id,
        )

        ssm.StringParameter(
            self,
            "AppClientIdParam",
            parameter_name="/grading/cognito/app-client-id",
            string_value=user_pool_client.user_pool_client_id,
        )
