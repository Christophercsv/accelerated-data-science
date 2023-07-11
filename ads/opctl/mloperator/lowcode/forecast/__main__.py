#!/usr/bin/env python
# -*- coding: utf-8 -*--

# Copyright (c) 2023 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

import os
import sys
import yaml
import json

from ads.opctl import logger
from ads.opctl.mloperator.common.utils import _parse_input_args

from .__init__ import __short_description__ as DESCRIPTION
from .__init__ import __name__ as MODULE
from .main import ForecastOperator, run

ENV_OPERATOR_ARGS = "ENV_OPERATOR_ARGS"


def main(raw_args):
    args, _ = _parse_input_args(raw_args)
    if not args.file and not args.spec and not os.environ.get(ENV_OPERATOR_ARGS):
        logger.info(
            "Please specify -f[--file] or -s[--spec] or "
            f"pass operator's arguments via {ENV_OPERATOR_ARGS} environment variable."
        )
        return

    logger.info("-" * 100)
    logger.info(f"Running operator: {MODULE}")
    logger.info(DESCRIPTION)

    # if spec provided as input string, then convert the string into YAML
    yaml_string = ""
    if args.spec or os.environ.get(ENV_OPERATOR_ARGS):
        operator_spec_str = args.spec or os.environ.get(ENV_OPERATOR_ARGS)
        try:
            yaml_string = yaml.safe_dump(json.loads(operator_spec_str))
        except json.JSONDecodeError:
            yaml_string = yaml.safe_dump(yaml.safe_load(operator_spec_str))
        except:
            yaml_string = operator_spec_str

    operator = ForecastOperator.from_yaml(
        uri=args.file,
        yaml_string=yaml_string,
    )

    logger.info(operator.to_yaml())

    run(operator)


if __name__ == "__main__":
    main(sys.argv[1:])
