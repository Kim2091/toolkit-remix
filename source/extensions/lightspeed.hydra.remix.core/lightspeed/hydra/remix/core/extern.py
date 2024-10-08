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

import ctypes
from enum import Enum
from typing import Callable

import carb

_instance = None
_GLOBAL_OBJECTPICKING_REQUESTID = 0


def dictcounted_push(dictcounted, key, value):
    existing_count = 0
    found = dictcounted.get(key)
    if found is not None:
        existing_count = found[0]
        if found[1] != value:
            carb.log_warn(
                f"dictcounted_push: Trying to push a new key-value pair: key={str(key)} already exists, "
                "so expecting existing value to match the value that is being added, "
                "however they mismatch. Overwriting the old one."
            )
            existing_count = 0
    dictcounted[key] = (existing_count + 1, value)


def dictcounted_pop(dictcounted, key):
    found = dictcounted.get(key)
    if found is not None:
        existing_count = found[0]
        value = found[1]
        if existing_count > 1:
            dictcounted[key] = (existing_count - 1, value)
        else:
            dictcounted.pop(key)
        return value
    return None


class RemixExtern:
    def __init__(self):
        self.__dll = RemixExtern.__load_dll()
        if self.__dll is None:
            return

        #
        # register C functions from the DLL
        #

        # void findworldposition_request( int requestid, int x, int y )
        self.__c_findworldposition_request = self.__dll.findworldposition_request
        self.__c_findworldposition_request.argtypes = (ctypes.c_int32, ctypes.c_int32, ctypes.c_int32)
        self.__c_findworldposition_request.restype = None

        # void objectpicking_request(uint32_t x0, uint32_t y0, uint32_t x1, uint32_t y1)
        self.__c_objectpicking_request = self.__dll.objectpicking_request
        self.__c_objectpicking_request.argtypes = (ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32)
        self.__c_objectpicking_request.restype = None

        # void objectpicking_highlight( const char **, uint32_t )
        self.__c_objectpicking_highlight = self.__dll.objectpicking_highlight
        self.__c_objectpicking_highlight.argtypes = (ctypes.POINTER(ctypes.c_char_p), ctypes.c_uint32)
        self.__c_objectpicking_highlight.restype = None

        # void hdremix_setconfigvariable( const char *, const char * )
        self.__c_hdremix_setconfigvariable = self.__dll.hdremix_setconfigvariable
        self.__c_hdremix_setconfigvariable.argtypes = (ctypes.c_char_p, ctypes.c_char_p)
        self.__c_hdremix_setconfigvariable.restype = None

        #
        # register C->Python callbacks, need to keep references alive
        #

        # callback begin: find world position
        self.__pywrap_findworldposition_oncomplete_t = ctypes.CFUNCTYPE(
            None, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_float, ctypes.c_float, ctypes.c_float
        )
        self.__pywrap_findworldposition_oncomplete = self.__pywrap_findworldposition_oncomplete_t(
            RemixExtern.__c_findworldposition_oncomplete
        )
        self.__dll.findworldposition_setcallback(self.__pywrap_findworldposition_oncomplete)
        # callback end

        # callback begin: object picking
        self.__pywrap_objectpicking_oncomplete_t = ctypes.CFUNCTYPE(
            None, ctypes.POINTER(ctypes.c_char_p), ctypes.c_uint32
        )
        self.__pywrap_objectpicking_oncomplete = self.__pywrap_objectpicking_oncomplete_t(
            RemixExtern.__c_objectpicking_oncomplete
        )
        self.__dll.objectpicking_setcallback_oncomplete(self.__pywrap_objectpicking_oncomplete)
        # callback end

        #

        # dict to track findworldposition / objectpicking request callbacks
        self.__requestdict_findworldposition = {}
        self.__requestdict_objectpicking = {}

    @staticmethod
    def __load_dll():
        try:
            dll = ctypes.cdll.LoadLibrary("HdRemix.dll")
        except FileNotFoundError:
            carb.log_warn("Failed to find HdRemix.dll. Object picking, highlighting are disabled")
            return None
        if (
            not hasattr(dll, "findworldposition_setcallback")
            or not hasattr(dll, "findworldposition_request")
            or not hasattr(dll, "objectpicking_highlight")
            or not hasattr(dll, "objectpicking_request")
            or not hasattr(dll, "objectpicking_setcallback_oncomplete")
            or not hasattr(dll, "hdremix_setconfigvariable")
        ):
            carb.log_warn(
                "HdRemix.dll doesn't contain the required functions. Object picking and highlighting are disabled"
            )
            return None
        return dll

    def findworldposition_request(self, pix_x: int, pix_y: int, callback, requestid: int):
        if self.__c_findworldposition_request is None:
            carb.log_error(
                "findworldposition_request fail: Couldn't load HdRemix.dll, "
                "or couldn't find 'findworldposition_request' function in it"
            )
            return
        self.__c_findworldposition_request(requestid, pix_x, pix_y)
        # save callback
        dictcounted_push(self.__requestdict_findworldposition, requestid, callback)

    # Called by HdRemix, when find world position request has been completed
    def findworldposition_oncomplete(
        self, requestid: int, pix_x: int, pix_y: int, world_x: float, world_y: float, world_z: float
    ):
        callback = dictcounted_pop(self.__requestdict_findworldposition, requestid)
        if callback is not None:
            callback(pix_x, pix_y, world_x, world_y, world_z)

    def objectpicking_request(self, x0: int, y0: int, x1: int, y1: int, callback, requestid):
        if self.__c_objectpicking_request is None:
            carb.log_error(
                "objectpicking_request fail: Couldn't load HdRemix.dll, "
                "or couldn't find 'objectpicking_request' function in it"
            )
            return
        self.__c_objectpicking_request(x0, y0, x1, y1)
        # save callback
        dictcounted_push(self.__requestdict_objectpicking, requestid, callback)

    # Called by HdRemix, when object picking request has been completed
    def objectpicking_oncomplete(self, requestid: int, selectedpaths):
        callback = dictcounted_pop(self.__requestdict_objectpicking, requestid)
        if callback is not None:
            callback(selectedpaths)

    def highlight_paths(self, paths):
        if self.__c_objectpicking_highlight is None:
            carb.log_error(
                "highlight_paths fail: Couldn't load HdRemix.dll, or couldn't find 'highlight_paths' function in it"
            )
            return
        # allocate const char*[], so C function can fill it
        c_string_array = (ctypes.c_char_p * len(paths))(*[p.encode("utf-8") for p in paths])
        self.__c_objectpicking_highlight(c_string_array, len(c_string_array))

    def set_configvar(self, key, value):
        if self.__c_hdremix_setconfigvariable is None:
            carb.log_error(
                "set_configvar fail: Couldn't load HdRemix.dll, or "
                "couldn't find 'hdremix_setconfigvariable' function in it"
            )
            return
        c_key = (key).encode("utf-8")
        c_value = value.encode("utf-8")
        self.__c_hdremix_setconfigvariable(c_key, c_value)

    @staticmethod
    def __c_findworldposition_oncomplete(
        requestid: int, pix_x: int, pix_y: int, world_x: float, world_y: float, world_z: float
    ):
        if _instance is None:
            return
        _instance.findworldposition_oncomplete(requestid, pix_x, pix_y, world_x, world_y, world_z)

    @staticmethod
    def __c_objectpicking_oncomplete(selectedpaths_cstr_values, selectedpaths_cstr_count):
        if _instance is None:
            return
        cstr_array = ctypes.cast(
            selectedpaths_cstr_values, ctypes.POINTER(ctypes.c_char_p * selectedpaths_cstr_count)
        ).contents
        selectedpaths = set()
        for i in range(selectedpaths_cstr_count):
            selectedpaths.add(cstr_array[i].decode("utf-8"))
        _instance.objectpicking_oncomplete(_GLOBAL_OBJECTPICKING_REQUESTID, selectedpaths)


def remix_extern_init():
    global _instance
    if _instance is None:
        _instance = RemixExtern()


def remix_extern_destroy():
    global _instance
    _instance = None


def safe_remix_extern() -> RemixExtern:
    remix_extern_init()
    return _instance


# Function ID to signed int32
def __callbackid_int32(callback, pix_x: int, pix_y: int) -> int:
    # incorporate pixel to increase chances of a unique request id
    return hash(id(callback) + 10 * pix_x + pix_y) & 0x7FFFFFFF


# callback( pix_x, pix_y, worldpos_x, worldpos_y, worldpos_z )
def hdremix_findworldposition_request(pix_x: int, pix_y: int, callback):
    safe_remix_extern().findworldposition_request(pix_x, pix_y, callback, __callbackid_int32(callback, pix_x, pix_y))


# callback( set_of_selected_usd_paths )
def hdremix_objectpicking_request(x0: int, y0: int, x1: int, y1: int, callback):
    safe_remix_extern().objectpicking_request(x0, y0, x1, y1, callback, _GLOBAL_OBJECTPICKING_REQUESTID)


def hdremix_highlight_paths(paths):
    safe_remix_extern().highlight_paths(paths)


# Directly set RtxOption of the Remix Renderer.
# Usage example: hdremix_set_configvar("rtx.fallbackLightType", "1")
# For the list of available options, see:
# https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/RtxOptions.md
def hdremix_set_configvar(key, value):
    safe_remix_extern().set_configvar(key, value)


class RemixRequestQueryType(Enum):
    PATH_AND_WORLDPOS = 0
    ONLY_WORLDPOS = 1
    ONLY_PATH = 2


# Compatibility function to replace viewport_api.request_query()
# callback( path, worldpos, pixel )
def viewport_api_request_query_hdremix(
    pixel: carb.Uint2,
    callback: Callable[[str, carb.Double3 | None, carb.Uint2], None] = None,
    query_name: str = "",
    request_query_type=RemixRequestQueryType.PATH_AND_WORLDPOS,
):
    if request_query_type == RemixRequestQueryType.ONLY_WORLDPOS:

        def get_only_worldpos(pix_x: int, pix_y: int, worldpos_x, worldpos_y, worldpos_z):
            callback("", carb.Double3(worldpos_x, worldpos_y, worldpos_z), carb.Uint2(pix_x, pix_y))

        hdremix_findworldposition_request(pixel[0], pixel[1], get_only_worldpos)
    elif request_query_type == RemixRequestQueryType.ONLY_PATH:

        def get_only_path(set_of_selected_usd_paths):
            path = next(iter(set_of_selected_usd_paths)) if len(set_of_selected_usd_paths) > 0 else ""
            callback(path, None, carb.Uint2(pixel[0], pixel[1]))

        hdremix_objectpicking_request(pixel[0], pixel[1], pixel[0] + 1, pixel[1] + 1, get_only_path)
    else:

        def get_path(set_of_selected_usd_paths):
            def get_worldpos(pix_x: int, pix_y: int, worldpos_x, worldpos_y, worldpos_z):
                path = next(iter(set_of_selected_usd_paths)) if len(set_of_selected_usd_paths) > 0 else ""
                worldpos = carb.Double3(worldpos_x, worldpos_y, worldpos_z) if path else None
                callback(path, worldpos, carb.Uint2(pix_x, pix_y))

            hdremix_findworldposition_request(pixel[0], pixel[1], get_worldpos)

        hdremix_objectpicking_request(pixel[0], pixel[1], pixel[0] + 1, pixel[1] + 1, get_path)
