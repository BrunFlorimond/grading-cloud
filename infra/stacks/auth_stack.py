from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_apigatewayv2 as apigatewayv2
from aws_cdk import aws_cognito as cognito

# TODO(#6): import aws_ssm for SSM parameter exports
# from aws_cdk import aws_ssm as ssm

from constructs import Construct


class AuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        user_pool = cognito.UserPool(
            self,
            "GradingUserPool",
            user_pool_name="grading-user-pool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=False),
            ),
            custom_attributes={
                "role": cognito.StringAttribute(
                    min_len=7,
                    max_len=7,
                    mutable=True,
                ),
            },
            # TODO(#6): add password_policy with min_length=8, require_uppercase=True,
            #           require_lowercase=True, require_digits=True, require_symbols=False
            # password_policy=cognito.PasswordPolicy(
            #     min_length=8,
            #     require_uppercase=True,
            #     require_lowercase=True,
            #     require_digits=True,
            #     require_symbols=False,
            # ),
        )

        cognito.CfnUserPoolGroup(
            self,
            "TeachersGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="Teachers",
            description="Teacher users for grading platform.",
        )

        cognito.CfnUserPoolGroup(
            self,
            "StudentsGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="Students",
            description="Student users for grading platform.",
        )

        user_pool_client = user_pool.add_client(
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

        # TODO(#6): export User Pool ID and App Client ID as SSM parameters
        # so other stacks and services can resolve them at deploy time without
        # hard-coded CloudFormation imports.
        #
        # ssm.StringParameter(
        #     self,
        #     "UserPoolIdParam",
        #     parameter_name="/grading/cognito/user-pool-id",
        #     string_value=user_pool.user_pool_id,
        # )
        #
        # ssm.StringParameter(
        #     self,
        #     "AppClientIdParam",
        #     parameter_name="/grading/cognito/app-client-id",
        #     string_value=user_pool_client.user_pool_client_id,
        # )
