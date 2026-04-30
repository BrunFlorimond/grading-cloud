#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.storage_stack import StorageStack

app = cdk.App()

StorageStack(
    app,
    "GradingStorageStack",
)

app.synth()
