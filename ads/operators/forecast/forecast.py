#!/usr/bin/env python
# -*- coding: utf-8 -*--

# Copyright (c) 2023 Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
import json
import logging
import os
import sys
import datapane as dp
from prophet.plot import add_changepoints_to_plot
import pandas as pd
from urllib.parse import urlparse
import json
import yaml
import time
import ads
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

import oci
import time
from datetime import datetime
from ads.operators.forecast.prophet import operate as prophet_operate
from ads.operators.forecast.prophet import get_prophet_report
from ads.operators.forecast.neural_prophet import operate as neuralprophet_operate
from ads.operators.forecast.neural_prophet import get_neuralprophet_report
from ads.operators.forecast.arima import operate as arima_operate

from ads.operators.forecast.utils import evaluate_metrics, test_evaluate_metrics
from sklearn.metrics import (
    mean_absolute_percentage_error,
    explained_variance_score,
    r2_score,
    mean_squared_error,
)
from sklearn.datasets import load_files

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

AVAILABLE_MODELS = ["prophet", "neuralprophet", "arima"]


class ForecastOperator:
    def __init__(self, args):
        self.args = args
        assert args["kind"] == "operator"
        assert args["type"] == "forecast"
        assert args["version"] == "1"
        self.historical_data = args["historical_data"]
        self.output_data = args["output_data"]
        self.model = args["forecast"]["model"].lower()
        self.target_columns = args["forecast"]["target_columns"]
        self.original_target_columns = args["forecast"]["target_columns"]
        self.target_category_column = args["forecast"]["target_category_column"]
        self.test_data = args["test_data"]
        self.datetime_column = args["forecast"]["datetime_column"]
        self.horizon = args["forecast"]["horizon"]
        self.report_file_name = args["forecast"]["report_file_name"]

        # TODO: clean up
        self.input_filename = self.historical_data["url"]
        self.output_filename = self.output_data["url"]
        self.test_filename = self.test_data["url"]
        self.ds_column = self.datetime_column.get("name")
        self.datetime_format = self.datetime_column.get("format")
        self.storage_options = {
            "profile": self.args["execution"].get("oci_profile"),
            "config": self.args["execution"].get("oci_config"),
        }

    def build_model(self):
        view = dp.View(dp.Text("# My report 3"))
        start_time = time.time()
        if self.model == "prophet":
            self.data, self.models, self.outputs = prophet_operate(self)
        elif self.model == "neuralprophet":
            self.data, self.models, self.outputs = neuralprophet_operate(self)
        elif self.model == "arima":
            self.data, self.models, self.outputs = arima_operate(self)
        else:
            raise ValueError(f"Unsupported model type: {self.model}")
        self.elapsed_time = time.time() - start_time
        return self.generate_report(self.elapsed_time)

    def generate_report(self, elapsed_time):
        def get_select_plot_list(fn):
            return dp.Select(
                blocks=[
                    dp.Plot(fn(i), label=col)
                    for i, col in enumerate(self.target_columns)
                ]
            )

        title_text = dp.Text("# Forecast Report")
        target_col_name = "yhat"
        train_metrics = True
        model_description = dp.Text("---")
        other_sections = []

        if self.model == "prophet":
            model_description = dp.Text(
                "Prophet is a procedure for forecasting time series data based on an additive model where non-linear trends are fit with yearly, weekly, and daily seasonality, plus holiday effects. It works best with time series that have strong seasonal effects and several seasons of historical data. Prophet is robust to missing data and shifts in the trend, and typically handles outliers well."
            )
            other_sections = get_prophet_report(self)
            ds_column_series = self.data["ds"]
        elif self.model == "neuralprophet":
            model_description = dp.Text(
                "NeuralProphet is an easy to learn framework for interpretable time series forecasting. NeuralProphet is built on PyTorch and combines Neural Network and traditional time-series algorithms, inspired by Facebook Prophet and AR-Net."
            )
            other_sections = get_neuralprophet_report(self)
            target_col_name = "yhat1"
            ds_column_series = self.data["ds"]
        elif self.model == "arima":
            model_description = dp.Text(
                "An autoregressive integrated moving average, or ARIMA, is a statistical analysis model that uses time series data to either better understand the data set or to predict future trends. A statistical model is autoregressive if it predicts future values based on past values."
            )
            train_metrics = False
            ds_column_series = self.data.index

        md_columns = " * ".join([f"{x} \n" for x in self.target_columns])
        summary = dp.Blocks(
            dp.Select(
                blocks=[
                    dp.Group(
                        dp.Text(f"You selected the **`{self.model}`** model."),
                        model_description,
                        dp.Text(
                            f"Based on your dataset, you could have also selected any of the models: `{'`, `'.join(AVAILABLE_MODELS)}`."
                        ),
                        dp.Group(
                            dp.BigNumber(
                                heading="Analysis was completed in (sec)",
                                value=int(elapsed_time),
                            ),
                            dp.BigNumber(
                                heading="Starting time index",
                                value=ds_column_series.min().strftime("%B %d, %Y"), # "%r" # TODO: Figure out a smarter way to format
                            ),
                            dp.BigNumber(
                                heading="Ending time index", value=ds_column_series.max().strftime("%B %d, %Y") # "%r" # TODO: Figure out a smarter way to format
                            ),
                            dp.BigNumber(heading="Num series", value=len(self.target_columns)),
                            columns=4,
                        ),
                        dp.DataTable(self.data.head(10), caption="Start"),
                        dp.Text("----"),
                        dp.DataTable(self.data.tail(10), caption="End"),
                        label="Summary",
                    ),
                    dp.Text(
                        f"The following report compares a variety of metrics and plots for your target columns: \n {md_columns}.\n",
                        label="Target Columns",
                    ),
                ]
            ),
        )

        train_metric_sections = []
        if train_metrics:
            self.eval_metrics = evaluate_metrics(
                self.target_columns, self.data, self.outputs, target_col=target_col_name
            )
            sec6_text = dp.Text(f"## Historical Data Evaluation Metrics")
            sec6 = dp.DataTable(self.eval_metrics)
            train_metric_sections = [sec6_text, sec6]

        test_eval_metrics = []
        if self.test_filename:
            self.test_eval_metrics, summary_metrics = test_evaluate_metrics(
                self.target_columns,
                self.test_filename,
                self.outputs,
                self,
                target_col=target_col_name,
            )
            sec7_text = dp.Text(f"## Holdout Data Evaluation Metrics")
            sec7 = dp.DataTable(self.test_eval_metrics)

            sec8_text = dp.Text(f"## Holdout Data Summary Metrics")
            sec8 = dp.DataTable(summary_metrics)

            test_eval_metrics = [sec7_text, sec7, sec8_text, sec8]

        yaml_appendix_title = dp.Text(f"## Reference: YAML File")
        yaml_appendix = dp.Code(code=yaml.dump(self.args), language="yaml")
        all_sections = (
            [title_text, summary]
            + other_sections
            + test_eval_metrics
            + train_metric_sections
            + [yaml_appendix_title, yaml_appendix]
        )
        self.view = dp.View(*all_sections)
        dp.save_report(self.view, self.report_file_name, open=True)
        print(f"Generated Report: {self.report_file_name}.")
        return


def operate(args):
    operator = ForecastOperator(args).build_model()
    return operator


def run():
    args = json.loads(os.environ.get("OPERATOR_ARGS", "{}"))
    return operate(args)


if __name__ == "__main__":
    run()