#!/usr/bin/env python
# -*- coding: utf-8 -*--

# Copyright (c) 2023 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

from typing import Any, Dict

import click

from ads.opctl.utils import suppress_traceback

from .__init__ import __operators__
from .cmd import info as cmd_info
from .cmd import list as cmd_list
from .cmd import init as cmd_init
from .cmd import create as cmd_create
from .cmd import build_image as cmd_build_image
from .cmd import publish_image as cmd_publish_image


@click.group("mloperator")
@click.help_option("--help", "-h")
def commands():
    pass


@commands.command()
@click.option("--debug", "-d", help="Set debug mode", is_flag=True, default=False)
def list(debug: bool, **kwargs: Dict[str, Any]) -> None:
    """Prints the list of the registered operators."""
    suppress_traceback(debug)(cmd_list)(**kwargs)


@commands.command()
@click.option("--debug", "-d", help="Set debug mode", is_flag=True, default=False)
@click.option(
    "--name",
    "-n",
    type=click.Choice(__operators__),
    help="The name of the operator",
    required=True,
)
def info(debug: bool, **kwargs: Dict[str, Any]) -> None:
    """Prints the detailed information about the particular operator."""
    suppress_traceback(debug)(cmd_info)(**kwargs)


@commands.command()
@click.option(
    "--name",
    "-n",
    type=click.Choice(__operators__),
    help="The name of the operator",
    required=True,
)
@click.option("--debug", "-d", help="Set debug mode", is_flag=True, default=False)
@click.option(
    "--output",
    help=f"The filename to save the resulting specification template YAML",
    required=False,
    default=None,
)
@click.option(
    "--overwrite",
    "-o",
    help="Overwrite result file if it already exists",
    is_flag=True,
    default=False,
)
@click.option(
    "--ads-config",
    help="The folder where the ADS opctl config located",
    required=False,
    default=None,
)
def init(debug: bool, **kwargs: Dict[str, Any]) -> None:
    """Generates a starter specification template YAML for the operator."""
    suppress_traceback(debug)(cmd_init)(**kwargs)


@commands.command()
@click.option("--debug", "-d", help="Set debug mode", is_flag=True, default=False)
@click.help_option("--help", "-h")
@click.option(
    "--gpu",
    "-g",
    help="Build a GPU-enabled Docker image.",
    is_flag=True,
    default=False,
    required=False,
)
@click.option(
    "--name",
    "-n",
    help=(
        "Name of the service operator to build the image. "
        "Only relevant for built-in service operators."
    ),
    default=None,
    required=False,
)
@click.option(
    "--source-folder",
    "-s",
    help=(
        "Use this option for custom operators. "
        "Specify the folder containing the operator source code."
    ),
    default=None,
    required=False,
)
@click.option(
    "--image",
    "-i",
    help="The image name. By default the operator name will be used.",
    default=None,
    required=False,
)
@click.option("--tag", "-t", help="The image tag.", required=False, default=None)
@click.option(
    "--rebuild-base-image",
    "-r",
    help="Rebuild both base and operator's images.",
    is_flag=True,
    default=False,
)
def build_image(debug: bool, **kwargs: Dict[str, Any]) -> None:
    """Builds a new image for the given operator."""
    suppress_traceback(debug)(cmd_build_image)(**kwargs)


@commands.command()
@click.option("--debug", "-d", help="Set debug mode", is_flag=True, default=False)
@click.help_option("--help", "-h")
@click.argument("image")
@click.option(
    "--registry", "-r", help="Registry to publish to", required=False, default=None
)
@click.option(
    "--ads-config",
    help="The folder where the ADS opctl config located",
    required=False,
    default=None,
)
def publish_image(debug, **kwargs):
    """Publishes operator image to the container registry."""
    suppress_traceback(debug)(cmd_publish_image)(**kwargs)


@commands.command()
@click.option(
    "--name",
    "-n",
    type=click.Choice(__operators__),
    help="The name of the operator",
    required=True,
)
@click.option("--debug", "-d", help="Set debug mode", is_flag=True, default=False)
@click.option(
    "--overwrite",
    "-o",
    help="Overwrite result file if it already exists",
    is_flag=True,
    default=False,
)
@click.option(
    "--ads-config",
    help="The folder where the ADS opctl config located",
    required=False,
    default=None,
)
def create(debug: bool, **kwargs: Dict[str, Any]) -> None:
    """Creates new operator."""
    suppress_traceback(debug)(cmd_create)(**kwargs)
