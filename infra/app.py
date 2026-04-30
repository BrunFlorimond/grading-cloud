#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.auth_stack import AuthStack
from stacks.storage_stack import StorageStack

app = cdk.App()

AuthStack(
    app,
    "GradingAuthStack",
)

StorageStack(
    app,
    "GradingStorageStack",
)

app.synth()
