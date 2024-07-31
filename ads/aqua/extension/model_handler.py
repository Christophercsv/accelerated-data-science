#!/usr/bin/env python
# Copyright (c) 2024 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

import re
from typing import Optional
from urllib.parse import urlparse

from huggingface_hub import HfApi
from huggingface_hub.utils import (
    GatedRepoError,
    HfHubHTTPError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)
from tornado.web import HTTPError

from ads.aqua.common.decorator import handle_exceptions
from ads.aqua.common.errors import AquaRuntimeError, AquaValueError
from ads.aqua.extension.base_handler import AquaAPIhandler
from ads.aqua.extension.errors import Errors
from ads.aqua.model import AquaModelApp
from ads.aqua.model.constants import ModelTask
from ads.aqua.model.entities import AquaModelSummary, HFModelSummary
from ads.aqua.ui import ModelFormat


class AquaModelHandler(AquaAPIhandler):
    """Handler for Aqua Model REST APIs."""

    @handle_exceptions
    def get(
        self,
        model_id="",
    ):
        """Handle GET request."""
        url_parse = urlparse(self.request.path)
        paths = url_parse.path.strip("/")
        if paths.startswith("aqua/model/files"):
            os_path = self.get_argument("os_path")
            if not os_path:
                raise HTTPError(
                    400, Errors.MISSING_REQUIRED_PARAMETER.format("os_path")
                )
            model_format = self.get_argument("model_format")
            if not model_format:
                raise HTTPError(
                    400, Errors.MISSING_REQUIRED_PARAMETER.format("model_format")
                )
            try:
                model_format = ModelFormat(model_format.upper())
            except ValueError as err:
                raise AquaValueError(f"Invalid model format: {model_format}") from err
            else:
                return self.finish(AquaModelApp.get_model_files(os_path, model_format))
        elif not model_id:
            return self.list()

        return self.read(model_id)

    def read(self, model_id):
        """Read the information of an Aqua model."""
        return self.finish(AquaModelApp().get(model_id))

    @handle_exceptions
    def delete(self):
        """Handles DELETE request for clearing cache"""
        url_parse = urlparse(self.request.path)
        paths = url_parse.path.strip("/")
        if paths.startswith("aqua/model/cache"):
            return self.finish(AquaModelApp().clear_model_list_cache())
        else:
            raise HTTPError(400, f"The request {self.request.path} is invalid.")

    def list(self):
        """List Aqua models."""
        compartment_id = self.get_argument("compartment_id", default=None)
        # project_id is no needed.
        project_id = self.get_argument("project_id", default=None)
        model_type = self.get_argument("model_type", default=None)
        return self.finish(
            AquaModelApp().list(
                compartment_id=compartment_id,
                project_id=project_id,
                model_type=model_type,
            )
        )

    @handle_exceptions
    def post(self, *args, **kwargs):
        """
        Handles post request for the registering any Aqua model.
        Raises
        ------
        HTTPError
            Raises HTTPError if inputs are missing or are invalid
        """
        try:
            input_data = self.get_json_body()
        except Exception as ex:
            raise HTTPError(400, Errors.INVALID_INPUT_DATA_FORMAT) from ex

        if not input_data:
            raise HTTPError(400, Errors.NO_INPUT_DATA)

        # required input parameters
        model = input_data.get("model")
        if not model:
            raise HTTPError(400, Errors.MISSING_REQUIRED_PARAMETER.format("model"))
        os_path = input_data.get("os_path")
        if not os_path:
            raise HTTPError(400, Errors.MISSING_REQUIRED_PARAMETER.format("os_path"))

        inference_container = input_data.get("inference_container")
        finetuning_container = input_data.get("finetuning_container")
        compartment_id = input_data.get("compartment_id")
        project_id = input_data.get("project_id")
        model_file = input_data.get("model_file")
        download_from_hf = (
            str(input_data.get("download_from_hf", "false")).lower() == "true"
        )

        return self.finish(
            AquaModelApp().register(
                model=model,
                os_path=os_path,
                download_from_hf=download_from_hf,
                inference_container=inference_container,
                finetuning_container=finetuning_container,
                compartment_id=compartment_id,
                project_id=project_id,
                model_file=model_file,
            )
        )


class AquaModelLicenseHandler(AquaAPIhandler):
    """Handler for Aqua Model license REST APIs."""

    @handle_exceptions
    def get(self, model_id):
        """Handle GET request."""

        model_id = model_id.split("/")[0]
        return self.finish(AquaModelApp().load_license(model_id))


class AquaHuggingFaceHandler(AquaAPIhandler):
    """Handler for Aqua Hugging Face REST APIs."""

    @staticmethod
    def _find_matching_aqua_model(model_id: str) -> Optional[AquaModelSummary]:
        """
        Finds a matching model in AQUA based on the model ID from Hugging Face.

        Parameters
        ----------
        model_id (str): The Hugging Face model ID to match.

        Returns
        -------
        Optional[AquaModelSummary]
            Returns the matching AquaModelSummary object if found, else None.
        """
        # Convert the Hugging Face model ID to lowercase once
        model_id_lower = model_id.lower()

        aqua_model_app = AquaModelApp()
        model_ocid = aqua_model_app._find_matching_aqua_model(model_id=model_id_lower)
        if model_ocid:
            return aqua_model_app.get(model_ocid, load_model_card=False)

        return None

    def _format_custom_error_message(self, error: HfHubHTTPError):
        """
        Formats a custom error message based on the Hugging Face error response.

        Parameters
        ----------
        error (HfHubHTTPError): The caught exception.

        Raises
        ------
        AquaRuntimeError: A user-friendly error message.
        """
        # Extract the repository URL from the error message if present
        match = re.search(r"(https://huggingface.co/[^\s]+)", str(error))
        url = match.group(1) if match else "the requested Hugging Face URL."

        if isinstance(error, RepositoryNotFoundError):
            raise AquaRuntimeError(
                reason=f"Failed to access `{url}`. Please check if the provided repository name is correct. "
                "If the repo is private, make sure you are authenticated and have a valid HF token registered. "
                "To register your token, run this command in your terminal: `huggingface-cli login`",
                service_payload={"error": "RepositoryNotFoundError"},
            )

        if isinstance(error, GatedRepoError):
            raise AquaRuntimeError(
                reason=f"Access denied to `{url}` "
                "This repository is gated. Access is restricted to authorized users. "
                "Please request access or check with the repository administrator. "
                "If you are trying to access a gated repository, ensure you have a valid HF token registered. "
                "To register your token, run this command in your terminal: `huggingface-cli login`",
                service_payload={"error": "GatedRepoError"},
            )

        if isinstance(error, RevisionNotFoundError):
            raise AquaRuntimeError(
                reason=f"The specified revision could not be found at `{url}` "
                "Please check the revision identifier and try again.",
                service_payload={"error": "RevisionNotFoundError"},
            )

        raise AquaRuntimeError(
            reason=f"An error occurred while accessing `{url}` "
            "Please check your network connection and try again. "
            "If you are trying to access a gated repository, ensure you have a valid HF token registered. "
            "To register your token, run this command in your terminal: `huggingface-cli login`",
            service_payload={"error": "Error"},
        )

    @handle_exceptions
    def post(self, *args, **kwargs):
        """Handles post request for the HF Models APIs

        Raises
        ------
        HTTPError
            Raises HTTPError if inputs are missing or are invalid.
        """
        try:
            input_data = self.get_json_body()
        except Exception as ex:
            raise HTTPError(400, Errors.INVALID_INPUT_DATA_FORMAT) from ex

        if not input_data:
            raise HTTPError(400, Errors.NO_INPUT_DATA)

        model_id = input_data.get("model_id")
        token = input_data.get("token")

        if not model_id:
            raise HTTPError(400, Errors.MISSING_REQUIRED_PARAMETER.format("model_id"))

        # Get model info from the HF
        try:
            hf_model_info = HfApi(token=token).model_info(model_id)
        except HfHubHTTPError as err:
            raise self._format_custom_error_message(err) from err

        # Check if model is not disabled
        if hf_model_info.disabled:
            raise AquaRuntimeError(
                f"The chosen model '{hf_model_info.id}' is currently disabled and cannot be imported into AQUA. "
                "Please verify the model's status on the Hugging Face Model Hub or select a different model."
            )

        # Check pipeline_tag, it should be `text-generation`
        if (
            not hf_model_info.pipeline_tag
            or hf_model_info.pipeline_tag.lower() != ModelTask.TEXT_GENERATION
        ):
            raise AquaRuntimeError(
                f"Unsupported pipeline tag for the chosen model: '{hf_model_info.pipeline_tag}'. "
                f"AQUA currently supports the following tasks only: {', '.join(ModelTask.values())}. "
                "Please select a model with a compatible pipeline tag."
            )

        # Check if it is a service/verified model
        aqua_model_info: AquaModelSummary = self._find_matching_aqua_model(
            model_id=hf_model_info.id
        )

        return self.finish(
            HFModelSummary(model_info=hf_model_info, aqua_model_info=aqua_model_info)
        )


__handlers__ = [
    ("model/?([^/]*)", AquaModelHandler),
    ("model/?([^/]*)/license", AquaModelLicenseHandler),
    ("model/hf/search/?([^/]*)", AquaHuggingFaceHandler),
]
