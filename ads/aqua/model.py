#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2024 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import List

import oci

from ads.aqua import logger
from ads.aqua.base import AquaApp
from ads.aqua.exception import AquaClientError, AquaServiceError
from ads.aqua.utils import (
    README,
    UNKNOWN,
    create_word_icon,
    get_artifact_path,
    read_file,
)
from ads.common.oci_resource import SEARCH_TYPE, OCIResource
from ads.common.serializer import DataClassSerializable
from ads.common.utils import get_console_link
from ads.config import (
    COMPARTMENT_OCID, 
    ODSC_MODEL_COMPARTMENT_OCID, 
    PROJECT_OCID, 
    TENANCY_OCID
)
from ads.model.datascience_model import DataScienceModel


class Tags(Enum):
    TASK = "task"
    LICENSE = "license"
    ORGANIZATION = "organization"
    AQUA_TAG = "OCI_AQUA"
    AQUA_SERVICE_MODEL_TAG = "aqua_service_model"
    AQUA_FINE_TUNED_MODEL_TAG = "aqua_fine_tuned_model"


@dataclass(repr=False)
class AquaModelSummary(DataClassSerializable):
    """Represents a summary of Aqua model."""

    compartment_id: str
    icon: str
    id: str
    is_fine_tuned_model: bool
    license: str
    name: str
    organization: str
    project_id: str
    tags: dict
    task: str
    time_created: str
    console_link: str


@dataclass(repr=False)
class AquaModel(AquaModelSummary, DataClassSerializable):
    """Represents an Aqua model."""

    model_card: str


class AquaModelApp(AquaApp):
    """Contains APIs for Aqua model.

    Attributes
    ----------

    Methods
    -------
    create(self, **kwargs) -> "AquaModel"
        Creates an instance of Aqua model.
    get(..., **kwargs)
        Gets the information of an Aqua model.
    list(...) -> List["AquaModelSummary"]
        List existing models created via Aqua.
    """

    def create(
        self, model_id: str, project_id: str, comparment_id: str = None, **kwargs
    ) -> DataScienceModel:
        """Creates custom aqua model from service model.

        Parameters
        ----------
        model_id: str
            The service model id.
        project_id: str
            The project id for custom model.
        comparment_id: str
            The compartment id for custom model. Defaults to None.
            If not provided, compartment id will be fetched from environment variables.

        Returns
        -------
        DataScienceModel:
            The instance of DataScienceModel.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                target_model = DataScienceModel.from_id(model_id)
                target_compartment = comparment_id or COMPARTMENT_OCID
                target_project = project_id or PROJECT_OCID

                if (
                    target_model.compartment_id == target_compartment
                    and target_model.project_id == target_project
                ):
                    logger.debug(
                        f"Aqua Model {model_id} exists in user's compartment and project. 
                        Skipped copying."
                    )
                    return target_model

                target_model.download_artifact(target_dir=temp_dir)
                custom_model = (
                    DataScienceModel()
                    .with_compartment_id(target_compartment)
                    .with_project_id(target_project)
                    .with_artifact(temp_dir)
                    .with_display_name(target_model.display_name)
                    .with_description(target_model.description)
                    .with_freeform_tags(**(target_model.freeform_tags or {}))
                    .with_defined_tags(**(target_model.defined_tags or {}))
                    .with_model_version_set_id(target_model.model_version_set_id)
                    .with_version_label(target_model.version_label)
                    .with_custom_metadata_list(target_model.custom_metadata_list)
                    .with_defined_metadata_list(target_model.defined_metadata_list)
                    .with_provenance_metadata(target_model.provenance_metadata)
                    # TODO: decide what kwargs will be needed.
                    .create(**kwargs)
                )
                logger.debug(
                    f"Aqua Model {custom_model.id} created with the service model {model_id}"
                )

                return custom_model
            except Exception as se:
                # TODO: adjust error raising
                logger.error(f"Failed to create model from the given id {model_id}.")
                raise AquaServiceError(
                    opc_request_id=se.request_id, status_code=se.code
                )

    def get(self, model_id) -> "AquaModel":
        """Gets the information of an Aqua model.

        Parameters
        ----------
        model_id: str
            The model OCID.

        Returns
        -------
        AquaModel:
            The instance of AquaModel.
        """
        try:
            oci_model = self.ds_client.get_model(model_id).data
        except Exception as se:
            # TODO: adjust error raising
            logger.error(f"Failed to retreive model from the given id {model_id}")
            raise AquaServiceError(opc_request_id=se.request_id, status_code=se.code)

        if not self._if_show(oci_model):
            raise AquaClientError(f"Target model {oci_model.id} is not Aqua model.")

        artifact_path = get_artifact_path(oci_model.custom_metadata_list)

        return AquaModel(
            **AquaModelApp.process_model(oci_model, self.region),
            project_id=oci_model.project_id,
            model_card=str(
                read_file(file_path=f"{artifact_path}/{README}", auth=self._auth)
            ),
        )

    def list(
        self, compartment_id: str = None, project_id: str = None, **kwargs
    ) -> List["AquaModelSummary"]:
        """List Aqua models in a given compartment and under certain project.

        Parameters
        ----------
        compartment_id: (str, optional). Defaults to `None`.
            The compartment OCID.
        project_id: (str, optional). Defaults to `None`.
            The project OCID.
        kwargs
            Additional keyword arguments.
        Returns
        -------
        List[AquaModelSummary]:
            The list of the `ads.aqua.model.AquaModelSummary`.
        """
        models = []
        if compartment_id:
            logger.info(f"Fetching custom models from compartment_id={compartment_id}.")
            models = self._rqs(compartment_id)
        else:
            logger.info(
                f"Fetching service model from compartment_id={ODSC_MODEL_COMPARTMENT_OCID}"
            )
            models = self.list_resource(
                self.ds_client.list_models, compartment_id=ODSC_MODEL_COMPARTMENT_OCID
            )

        logger.info(
            f"Fetch {len(models)} model in compartment_id={compartment_id or ODSC_MODEL_COMPARTMENT_OCID}."
        )

        aqua_models = []
        # TODO: build index.json for service model as caching if needed.

        for model in models:
            aqua_models.append(
                AquaModelSummary(
                    **AquaModelApp.process_model(model=model, region=self.region),
                    project_id=project_id or UNKNOWN,
                )
            )

        return aqua_models

    @classmethod
    def process_model(cls, model, region) -> dict:
        icon = cls()._load_icon(model.display_name)
        tags = {}
        tags.update(model.defined_tags or {})
        tags.update(model.freeform_tags or {})

        model_id = (
            model.id
            if (
                isinstance(model, oci.data_science.models.ModelSummary)
                or isinstance(model, oci.data_science.models.model.Model)
            )
            else model.identifier
        )
        console_link = (
            get_console_link(
                resource="models",
                ocid=model_id,
                region=region,
            ),
        )

        return dict(
            compartment_id=model.compartment_id,
            icon=icon,
            id=model_id,
            license=model.freeform_tags.get(Tags.LICENSE.value, UNKNOWN),
            name=model.display_name,
            organization=model.freeform_tags.get(Tags.ORGANIZATION.value, UNKNOWN),
            task=model.freeform_tags.get(Tags.TASK.value, UNKNOWN),
            time_created=model.time_created,
            is_fine_tuned_model=(
                True
                if model.freeform_tags.get(Tags.AQUA_FINE_TUNED_MODEL_TAG.value)
                else False
            ),
            tags=tags,
            console_link=console_link,
        )

    def _if_show(self, model: "AquaModel") -> bool:
        """Determine if the given model should be return by `list`."""
        TARGET_TAGS = model.freeform_tags.keys()
        return (
            Tags.AQUA_TAG.value in TARGET_TAGS
            or Tags.AQUA_TAG.value.lower() in TARGET_TAGS
        )

    def _load_icon(self, model_name) -> str:
        """Loads icon."""

        # TODO: switch to the official logo
        try:
            return create_word_icon(model_name, return_as_datauri=True)
        except Exception as e:
            logger.error(f"Failed to load icon for the model={model_name}.")
            return None

    def _rqs(self, compartment_id):
        """Use RQS to fetch models in the user tenancy."""
        condition_tags = f"&& (freeformTags.key = '{Tags.AQUA_TAG.value}' && freeformTags.key = '{Tags.AQUA_FINE_TUNED_MODEL_TAG.value}')"
        condition_lifecycle = "&& lifecycleState = 'ACTIVE'"
        query = f"query datasciencemodel resources where (compartmentId = '{compartment_id}' {condition_lifecycle} {condition_tags})"
        logger.info(query)
        logger.info(f"tenant_id={TENANCY_OCID}")
        try:
            return OCIResource.search(
                query,
                type=SEARCH_TYPE.STRUCTURED,
                tenant_id=TENANCY_OCID,
            )
        except Exception as se:
            # TODO: adjust error raising
            logger.error(
                f"Failed to retreive model from the given compartment {compartment_id}"
            )
            raise AquaServiceError(opc_request_id=se.request_id, status_code=se.code)
