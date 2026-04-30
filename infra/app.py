#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.auth_stack import AuthStack
from stacks.compute_stack import ComputeStack
from stacks.storage_stack import StorageStack

app = cdk.App()

storage_stack = StorageStack(
    app,
    "GradingStorageStack",
)

AuthStack(
    app,
    "GradingAuthStack",
)

ComputeStack(
    app,
    "GradingComputeStack",
    files_bucket=storage_stack.files_bucket,
    grading_table=storage_stack.grading_table,
)

app.synth()
