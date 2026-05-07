#!/usr/bin/env python3

import os

import aws_cdk as cdk

from stacks.auth_stack import AuthStack
from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.storage_stack import StorageStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION"),
)

storage_stack = StorageStack(app, "GradingStorageStack", env=env)
auth_stack = AuthStack(app, "GradingAuthStack", env=env)
database_stack = DatabaseStack(app, "GradingDatabaseStack", env=env)
ComputeStack(
    app,
    "GradingComputeStack",
    files_bucket=storage_stack.files_bucket,
    vpc=database_stack.vpc,
    db_secret=database_stack.db_secret,
    db_endpoint=database_stack.db_instance.db_instance_endpoint_address,
    db_name="grading",
    user_pool_id=auth_stack.user_pool.user_pool_id,
    app_client_id=auth_stack.user_pool_client.user_pool_client_id,
    alb_sg=database_stack.alb_sg,
    fargate_sg=database_stack.fargate_sg,
    env=env,
)

app.synth()
