"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import abc
import platform
import shutil
import subprocess
import tempfile
from enum import Enum
from pathlib import Path

import carb
from lightspeed.common import constants as _constants


class BaseUpscaleModel:
    @property
    @abc.abstractmethod
    def name(self) -> str:
        return "BaseModel"

    @abc.abstractmethod
    def perform(self, input_path: Path, output_path: Path):
        pass


class EsrganUpscaleModel(BaseUpscaleModel):
    @property
    def name(self) -> str:
        return "ESRGAN"

    def perform(self, input_path: Path, output_path: Path):
        esrgan_tool_path = Path(_constants.REAL_ESRGAN_ROOT_PATH) / "realesrgan-ncnn-vulkan.exe"

        with subprocess.Popen(
            [str(esrgan_tool_path), "-i", str(input_path), "-o", str(output_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        ) as upscale_process:
            upscale_process.wait()


class SR3UpscaleModel(BaseUpscaleModel):
    @property
    def name(self) -> str:
        return "SR3+"

    def perform(self, input_path: Path, output_path: Path):
        sr3_tool_path = Path(_constants.MAT_SR_ROOT_PATH) / "app" / "app.py"
        sr3_python_path = (
            Path(_constants.MAT_SR_ROOT_PATH)
            / "tools"
            / "packman"
            / ("python.bat" if platform.system() == "Windows" else "python.sh")
        )

        sr3_artifacts_base_path = (
            Path(_constants.MAT_SR_ARTIFACTS_ROOT_PATH) / "diffusionSR" / "MATSR3_diffuse_X4" / "250223_160k"
        )
        sr3_config_path = sr3_artifacts_base_path / "config.yaml"
        sr3_model_path = sr3_artifacts_base_path / "model_latest.pth.tar"

        with tempfile.TemporaryDirectory() as temp_dir:
            with subprocess.Popen(
                [
                    str(sr3_python_path),
                    str(sr3_tool_path),
                    "--config",
                    str(sr3_config_path),
                    "--model",
                    str(sr3_model_path),
                    "run",
                    str(input_path),
                    "--outdir",
                    temp_dir,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            ) as upscale_process:
                upscale_process.wait()

            upscaled_texture = Path(temp_dir) / input_path.stem / "diffuse.png"
            upscaled_output_texture = output_path.with_suffix(".png")

            if upscaled_texture.exists():
                carb.log_info(f"Moving Upscaled Image from '{upscaled_texture}' to '{upscaled_output_texture}'")
                shutil.move(str(upscaled_texture), str(upscaled_output_texture))
            else:
                carb.log_warn(f"Unable to find upscaled texture: {upscaled_texture}")


class UpscaleModels(Enum):
    ESRGAN = EsrganUpscaleModel()
    SR3 = SR3UpscaleModel()
