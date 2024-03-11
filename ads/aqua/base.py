#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2024 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/


from typing import Dict, Union
import oci

from ads import set_auth
from ads.aqua.exception import AquaValueError
from ads.aqua.utils import UNKNOWN, is_valid_ocid, logger
from ads.common import oci_client as oc
from ads.common.auth import default_signer
from ads.common.utils import extract_region
from ads.model.datascience_model import DataScienceModel
from ads.model.deployment.model_deployment import ModelDeployment
from ads.model.model_metadata import ModelCustomMetadata, ModelProvenanceMetadata, ModelTaxonomyMetadata
from ads.model.model_version_set import ModelVersionSet

from oci.data_science.models import (
    UpdateModelDetails,
    UpdateModelProvenanceDetails,
)
from ads.config import (
    OCI_ODSC_SERVICE_ENDPOINT,
    OCI_RESOURCE_PRINCIPAL_VERSION,
    AQUA_CONFIG_FOLDER,
)

from ads.aqua.data import Tags
from ads.aqua.exception import AquaRuntimeError, AquaValueError
from ads.aqua.utils import load_config


class AquaApp:
    """Base Aqua App to contain common components."""

    def __init__(self) -> None:
        if OCI_RESOURCE_PRINCIPAL_VERSION:
            set_auth("resource_principal")
        self._auth = default_signer({"service_endpoint": OCI_ODSC_SERVICE_ENDPOINT})
        self.ds_client = oc.OCIClientFactory(**self._auth).data_science
        self.logging_client = oc.OCIClientFactory(**default_signer()).logging_management
        self.identity_client = oc.OCIClientFactory(**default_signer()).identity
        self.region = extract_region(self._auth)

    def list_resource(
        self,
        list_func_ref,
        **kwargs,
    ) -> list:
        """Generic method to list OCI Data Science resources.

        Parameters
        ----------
        list_func_ref : function
            A reference to the list operation which will be called.
        **kwargs :
            Additional keyword arguments to filter the resource.
            The kwargs are passed into OCI API.

        Returns
        -------
        list
            A list of OCI Data Science resources.
        """
        return oci.pagination.list_call_get_all_results(
            list_func_ref,
            **kwargs,
        ).data
    
    def update_model(
        self,
        model_id: str,
        update_model_details: UpdateModelDetails
    ):
        """Updates model details.

        Parameters
        ----------
        model_id : str
            The id of target model.
        update_model_details: UpdateModelDetails
            The model details to be updated.
        """
        self.ds_client.update_model(
            model_id=model_id,
            update_model_details=update_model_details
        )

    def update_model_provenance(
        self,
        model_id: str,
        update_model_provenance_details: UpdateModelProvenanceDetails
    ):
        """Updates model provenance details.

        Parameters
        ----------
        model_id : str
            The id of target model.
        update_model_provenance_details: UpdateModelProvenanceDetails
            The model provenance details to be updated.
        """
        self.ds_client.update_model_provenance(
            model_id=model_id,
            update_model_provenance_details=update_model_provenance_details
        )
    
    # TODO: refactor model evaluation implementation to use it.
    @staticmethod
    def get_source(source_id: str) -> Union[ModelDeployment, DataScienceModel]:
        if is_valid_ocid(source_id):
            if "datasciencemodeldeployment" in source_id:
                return ModelDeployment.from_id(source_id)
            elif "datasciencemodel" in source_id:
                return DataScienceModel.from_id(source_id)
        
        raise AquaValueError(
            f"Invalid source {source_id}. "
            "Specify either a model or model deployment id."
        )
    
    # TODO: refactor model evaluation implementation to use it.
    @staticmethod
    def create_model_version_set(
        model_version_set_id: str=None,
        model_version_set_name: str=None,
        description: str=None,
        compartment_id: str=None,
        project_id: str=None,
        **kwargs
    ) -> tuple:
        if not model_version_set_id:
            try:
                model_version_set = ModelVersionSet.from_name(
                    name=model_version_set_name,
                    compartment_id=compartment_id,
                )
            except:
                logger.debug(
                    f"Model version set {model_version_set_name} doesn't exist. "
                    "Creating new model version set."
                )
                model_version_set = (
                    ModelVersionSet()
                    .with_compartment_id(compartment_id)
                    .with_project_id(project_id)
                    .with_name(model_version_set_name)
                    .with_description(description)
                    # TODO: decide what parameters will be needed
                    .create(**kwargs)
                )
                logger.debug(
                    f"Successfully created model version set {model_version_set_name} with id {model_version_set.id}."
                )
            return (model_version_set.id, model_version_set_name)
        else:
            model_version_set = ModelVersionSet.from_id(model_version_set_id)
            return (model_version_set_id, model_version_set.name)
    
    # TODO: refactor model evaluation implementation to use it.
    @staticmethod
    def create_model_catalog(
        display_name: str,
        description: str,
        model_version_set_id: str,
        model_custom_metadata: Union[ModelCustomMetadata, Dict],
        model_taxonomy_metadata: Union[ModelTaxonomyMetadata, Dict],
        compartment_id: str,
        project_id: str,
        **kwargs
    ) -> DataScienceModel:
        model = (
            DataScienceModel()
            .with_compartment_id(compartment_id)
            .with_project_id(project_id)
            .with_display_name(display_name)
            .with_description(description)
            .with_model_version_set_id(model_version_set_id)
            .with_custom_metadata_list(model_custom_metadata)
            .with_defined_metadata_list(model_taxonomy_metadata)
            .with_provenance_metadata(
                ModelProvenanceMetadata(training_id=UNKNOWN)
            )
            # TODO: decide what parameters will be needed
            .create(
                **kwargs,
            )
        )
        return model

    def get_config(self, model_id: str, config_file_name: str) -> Dict:
        """Gets the config for the given Aqua model.
        Parameters
        ----------
        model_id: str
            The OCID of the Aqua model.
        config_file_name: str
            name of the config file

        Returns
        -------
        Dict:
            A dict of allowed configs.
        """
        oci_model = self.ds_client.get_model(model_id).data
        model_name = oci_model.display_name

        oci_aqua = (
            (
                Tags.AQUA_TAG.value in oci_model.freeform_tags
                or Tags.AQUA_TAG.value.lower() in oci_model.freeform_tags
            )
            if oci_model.freeform_tags
            else False
        )

        if not oci_aqua:
            raise AquaRuntimeError(f"Target model {oci_model.id} is not Aqua model.")

        # todo: currently loads config within ads, artifact_path will be an external bucket
        artifact_path = AQUA_CONFIG_FOLDER
        config = load_config(
            artifact_path,
            config_file_name=config_file_name,
        )

        if model_name not in config:
            raise AquaValueError(
                f"{config_file_name} does not have config details for model: {model_name}"
            )

        return config[model_name]
