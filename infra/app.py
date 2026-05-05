#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.auth_stack import AuthStack
from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.storage_stack import StorageStack

app = cdk.App()

storage_stack = StorageStack(app, "GradingStorageStack")
AuthStack(app, "GradingAuthStack")
database_stack = DatabaseStack(app, "GradingDatabaseStack")
ComputeStack(
    app,
    "GradingComputeStack",
    files_bucket=storage_stack.files_bucket,
    vpc=database_stack.vpc,
    db_secret=database_stack.db_secret,
    alb_sg=database_stack.alb_sg,
    fargate_sg=database_stack.fargate_sg,
)

app.synth()
