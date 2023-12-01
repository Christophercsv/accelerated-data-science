#!/usr/bin/env python
# -*- coding: utf-8 -*--

# Copyright (c) 2023 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

import base64
import json
import os
import tempfile
from copy import deepcopy
from typing import Any, Dict, List, Optional

import fsspec
import yaml
from langchain import llms
from langchain.chains import RetrievalQA
from langchain.chains.loading import load_chain_from_config
from langchain.llms import loading
from langchain.load import dumpd
from langchain.load.load import load as __lc_load
from langchain.load.load import Reviver
from langchain.load.serializable import Serializable
from langchain.vectorstores import FAISS, OpenSearchVectorSearch
from opensearchpy.client import OpenSearch

from ads.common.auth import default_signer
from ads.common.object_storage_details import ObjectStorageDetails
from ads.llm import GenerativeAI, ModelDeploymentTGI, ModelDeploymentVLLM
from ads.llm.chain import GuardrailSequence
from ads.llm.guardrails.base import CustomGuardrailBase
from ads.llm.patch import RunnableParallel, RunnableParallelSerializer

# This is a temp solution for supporting custom LLM in legacy load_chain
__lc_llm_dict = llms.get_type_to_cls_dict()
__lc_llm_dict[GenerativeAI.__name__] = lambda: GenerativeAI
__lc_llm_dict[ModelDeploymentTGI.__name__] = lambda: ModelDeploymentTGI
__lc_llm_dict[ModelDeploymentVLLM.__name__] = lambda: ModelDeploymentVLLM


def __new_type_to_cls_dict():
    return __lc_llm_dict


llms.get_type_to_cls_dict = __new_type_to_cls_dict
loading.get_type_to_cls_dict = __new_type_to_cls_dict


class OpenSearchVectorDBSerializer:
    """
    Serializer for OpenSearchVectorSearch class
    """
    @staticmethod
    def type():
        return OpenSearchVectorSearch.__name__

    @staticmethod
    def load(config: dict, **kwargs):
        config["kwargs"]["embedding_function"] = load(
            config["kwargs"]["embedding_function"], **kwargs
        )
        return OpenSearchVectorSearch(
            **config["kwargs"],
            http_auth=(
                os.environ.get("OCI_OPENSEARCH_USERNAME", None),
                os.environ.get("OCI_OPENSEARCH_PASSWORD", None),
            ),
            verify_certs=True if os.environ.get("OCI_OPENSEARCH_VERIFY_CERTS", None).lower() == "true" else False,
            ca_certs=os.environ.get("OCI_OPENSEARCH_CA_CERTS", None),
        )

    @staticmethod
    def save(obj):
        serialized = dumpd(obj)
        serialized["type"] = "constructor"
        serialized["_type"] = OpenSearchVectorDBSerializer.type()
        kwargs = {}
        for key, val in obj.__dict__.items():
            if key == "client":
                if isinstance(val, OpenSearch):
                    client_info = val.transport.hosts[0]
                    opensearch_url = (
                        f"https://{client_info['host']}:{client_info['port']}"
                    )
                    kwargs.update({"opensearch_url": opensearch_url})
                else:
                    raise NotImplementedError("Only support OpenSearch client.")
                continue
            kwargs[key] = dump(val)
        serialized["kwargs"] = kwargs
        return serialized


class FaissSerializer:
    """
    Serializer for OpenSearchVectorSearch class
    """
    @staticmethod
    def type():
        return FAISS.__name__

    @staticmethod
    def load(config: dict, **kwargs):
        embedding_function = load(config["embedding_function"], **kwargs)
        decoded_pkl = base64.b64decode(json.loads(config["vectordb"]))
        return FAISS.deserialize_from_bytes(
            embeddings=embedding_function, serialized=decoded_pkl
        )  # Load the index

    @staticmethod
    def save(obj):
        serialized = {}
        serialized["_type"] = FaissSerializer.type()
        pkl = obj.serialize_to_bytes()
        # Encoding bytes to a base64 string
        encoded_pkl = base64.b64encode(pkl).decode('utf-8')
        # Serializing the base64 string
        serialized["vectordb"] = json.dumps(encoded_pkl)
        serialized["embedding_function"] = dump(obj.__dict__["embedding_function"])
        return serialized

# Mapping class to vector store serialization functions
vectordb_serialization = {"OpenSearchVectorSearch": OpenSearchVectorDBSerializer, "FAISS": FaissSerializer}


class RetrievalQASerializer:
    """
    Serializer for RetrieverQA class
    """
    @staticmethod
    def type():
        return "retrieval_qa"

    @staticmethod
    def load(config: dict, **kwargs):
        config_param = deepcopy(config)
        retriever_kwargs = config_param.pop("retriever_kwargs")
        vectordb_serializer = vectordb_serialization[config_param["vectordb"]["class"]]
        vectordb = vectordb_serializer.load(config_param.pop("vectordb"), **kwargs)
        retriever = vectordb.as_retriever(**retriever_kwargs)
        return load_chain_from_config(config=config_param, retriever=retriever)

    @staticmethod
    def save(obj):
        serialized = obj.dict()
        retriever_kwargs = {}
        for key, val in obj.retriever.__dict__.items():
            if key not in ["tags", "metadata", "vectorstore"]:
                retriever_kwargs[key] = val
        serialized["retriever_kwargs"] = retriever_kwargs
        serialized["vectordb"] = {"class": obj.retriever.vectorstore.__class__.__name__}

        vectordb_serializer = vectordb_serialization[serialized["vectordb"]["class"]]
        serialized["vectordb"].update(
            vectordb_serializer.save(obj.retriever.vectorstore)
        )

        if serialized["vectordb"]["class"] not in vectordb_serialization:
            raise NotImplementedError(
                f"VectorDBSerializer for {serialized['vectordb']['class']} is not implemented."
            )
        return serialized


# Mapping class to custom serialization functions
custom_serialization = {
    GuardrailSequence: GuardrailSequence.save,
    CustomGuardrailBase: CustomGuardrailBase.save,
    RunnableParallel: RunnableParallelSerializer.save,
    RetrievalQA: RetrievalQASerializer.save,
}

# Mapping _type to custom deserialization functions
# Note that the load function should take **kwargs
custom_deserialization = {
    GuardrailSequence.type(): GuardrailSequence.load,
    CustomGuardrailBase.type(): CustomGuardrailBase.load,
    RunnableParallelSerializer.type(): RunnableParallelSerializer.load,
    RetrievalQASerializer.type(): RetrievalQASerializer.load,
}


def load(
    obj: Any,
    *,
    secrets_map: Optional[Dict[str, str]] = None,
    valid_namespaces: Optional[List[str]] = None,
    **kwargs,
) -> Any:
    """Revive an ADS/LangChain class from a JSON object. Use this if you already
    have a parsed JSON object, eg. from `json.load` or `json.loads`.

    This is a drop in replacement for load() in langchain.load.load to support loading compatible class from ADS.

    Args:
        obj: The object to load.
        secrets_map: A map of secrets to load.
        valid_namespaces: A list of additional namespaces (modules)
            to allow to be deserialized.

    Returns:
        Revived LangChain objects.
    """
    # Add ADS as valid namespace
    if not valid_namespaces:
        valid_namespaces = []
    if "ads" not in valid_namespaces:
        valid_namespaces.append("ads")

    reviver = Reviver(secrets_map, valid_namespaces)

    def _load(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "_type" in obj and obj["_type"] in custom_deserialization:
                if valid_namespaces:
                    kwargs["valid_namespaces"] = valid_namespaces
                if secrets_map:
                    kwargs["secret_map"] = secrets_map
                return custom_deserialization[obj["_type"]](obj, **kwargs)
            # Need to revive leaf nodes before reviving this node
            loaded_obj = {k: _load(v) for k, v in obj.items()}
            return reviver(loaded_obj)
        if isinstance(obj, list):
            return [_load(o) for o in obj]
        return obj

    if isinstance(obj, dict) and "_type" in obj:
        obj_type = obj["_type"]
        # Check if the object has custom load function.
        if obj_type in custom_deserialization:
            if valid_namespaces:
                kwargs["valid_namespaces"] = valid_namespaces
            if secrets_map:
                kwargs["secret_map"] = secrets_map
            return custom_deserialization[obj_type](obj, **kwargs)
        # Legacy chain
        return load_chain_from_config(obj, **kwargs)

    return __lc_load(obj, secrets_map=secrets_map, valid_namespaces=valid_namespaces)


def load_from_yaml(
    uri: str,
    *,
    secrets_map: Optional[Dict[str, str]] = None,
    valid_namespaces: Optional[List[str]] = None,
    **kwargs,
):
    """Revive an ADS/LangChain class from a YAML file."""

    class _SafeLoaderIgnoreUnknown(yaml.SafeLoader):
        """Loader ignoring unknown tags in YAML"""

        def ignore_unknown(self, node):
            """Ignores unknown tags in YAML"""
            return node.value[0].value

    _SafeLoaderIgnoreUnknown.add_constructor(
        None, _SafeLoaderIgnoreUnknown.ignore_unknown
    )

    storage_options = default_signer() if ObjectStorageDetails.is_oci_path(uri) else {}

    with fsspec.open(uri, **storage_options) as f:
        config = yaml.load(f, Loader=_SafeLoaderIgnoreUnknown)

    return load(
        config, secrets_map=secrets_map, valid_namespaces=valid_namespaces, **kwargs
    )


def default(obj: Any) -> Any:
    """Calls the to_json() method to serialize the object.

    Parameters
    ----------
    obj : Any
        The object to be serialized.

    Returns
    -------
    Any
        The serialized representation of the object.

    Raises
    ------
    TypeError
        If the object is not LangChain serializable.
    """
    for super_class, save_fn in custom_serialization.items():
        if isinstance(obj, super_class):
            return save_fn(obj)
    if isinstance(obj, Serializable) and obj.is_lc_serializable():
        return obj.to_json()
    raise TypeError(f"Serialization of {type(obj)} is not supported.")


def __save(obj):
    """Calls the legacy save method to save the object to temp json
    then load it into a dictionary.
    """
    try:
        temp_file = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False
        )
        temp_file.close()
        obj.save(temp_file.name)
        with open(temp_file.name, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        os.unlink(temp_file.name)


def dump(obj: Any) -> Dict[str, Any]:
    """Return a json dict representation of an object.

    This is a drop in replacement of the dumpd() in langchain.load.dump
    to support serializing legacy LangChain chain and ADS GuardrailSequence.

    This method will raise TypeError when the object is not serializable.
    """
    for super_class, save_fn in custom_serialization.items():
        if isinstance(obj, super_class):
            return save_fn(obj)
    if (
        isinstance(obj, Serializable)
        and not obj.is_lc_serializable()
        and hasattr(obj, "save")
    ):
        # The object is not is_lc_serializable.
        # However, it supports the legacy save() method.
        return __save(obj)
    # The object is is_lc_serializable.
    # However, some properties may not be serializable
    # Here we try to dump the object and fallback to the save() method
    # if there is an error.
    try:
        return json.loads(json.dumps(obj, default=default))
    except TypeError as ex:
        if isinstance(obj, Serializable) and hasattr(obj, "save"):
            return __save(obj)
        raise ex
