# forza - ReXGlue Recompiled Project (Forza Horizon, 4D5309C9)
#
# SDK boilerplate lives in generated/rexglue.cmake. The codegen-on-first-configure,
# cross-build and patched-GPU-plugin blocks are adapted from RecompiledHaloReach.

cmake_minimum_required(VERSION 3.25)
project(forza LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Which executable: the disc's (0) or Title Update 4 (4): its own manifest, hints
# (hints_tu4/) and codegen output (generated_tu4/), docs/dlc.md.
set(FORZA_TITLE_UPDATE 0 CACHE STRING "Game version to build: 0 (base) or 4 (Title Update 4)")
set_property(CACHE FORZA_TITLE_UPDATE PROPERTY STRINGS 0 4)
if(FORZA_TITLE_UPDATE STREQUAL "4")
    set(FORZA_MANIFEST forza_manifest_tu4.toml)
    set(FORZA_GENERATED generated_tu4)
elseif(FORZA_TITLE_UPDATE STREQUAL "0")
    set(FORZA_MANIFEST forza_manifest.toml)
    set(FORZA_GENERATED generated)
else()
    message(FATAL_ERROR "FORZA_TITLE_UPDATE must be 0 or 4")
endif()

# Builds handed a finished generated/ (CI building from the private copy of the codegen
# output) have no default.xex to run codegen on.
option(FORZA_SKIP_CODEGEN "Compile generated/ as it is, never run codegen" OFF)
if(FORZA_SKIP_CODEGEN AND NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${FORZA_GENERATED}/default/sources.cmake")
    message(FATAL_ERROR "FORZA_SKIP_CODEGEN is on but ${FORZA_GENERATED}/default has no codegen output")
endif()

# Codegen runs the patched SDK overlay's rexglue when there is one: tools/build_rexglue_sdk.sh
# builds it from patches/rexglue-sdk/, and some patches change the generated code (0025:
# Xenon's dot products give QNaN on overflow, which the collision GJK depends on).
set(FORZA_REXGLUE "$ENV{HOME}/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64/bin/rexglue"
    CACHE FILEPATH "Patched rexglue to run codegen with instead of the SDK's")

# generated/rexglue.cmake lists the generated sources at configure time, so on a fresh
# checkout (no generated/default yet) codegen runs here once; otherwise the first build
# would run it but compile none of its output.
if(NOT CMAKE_CROSSCOMPILING AND NOT REXSDK_DIR AND
   NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${FORZA_GENERATED}/default/sources.cmake")
    find_package(rexglue 0.10.0 REQUIRED CONFIG)
    get_target_property(_rexglue rex::rexglue LOCATION)
    if(EXISTS "${FORZA_REXGLUE}")
        set(_rexglue "${FORZA_REXGLUE}")
    endif()
    message(STATUS "First configure: running codegen (${_rexglue}), this takes a while")
    execute_process(
        COMMAND "${_rexglue}" codegen "${CMAKE_CURRENT_SOURCE_DIR}/${FORZA_MANIFEST}"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        COMMAND_ERROR_IS_FATAL ANY)
endif()

# generated/rexglue.cmake is rewritten by every codegen run, with the paths of the manifest
# that ran (generated/ or generated_tu4/); this build includes a copy pointed at its own.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/generated/rexglue.cmake" _rexglue_cmake)
string(REGEX REPLACE "generated(_tu4)?/default" "${FORZA_GENERATED}/default" _rexglue_cmake "${_rexglue_cmake}")
string(REGEX REPLACE "forza_manifest(_tu4)?\\.toml" "${FORZA_MANIFEST}" _rexglue_cmake "${_rexglue_cmake}")
file(CONFIGURE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/rexglue_project.cmake" CONTENT "${_rexglue_cmake}" @ONLY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/generated/rexglue.cmake")
include("${CMAKE_CURRENT_BINARY_DIR}/rexglue_project.cmake")

# A cross build compiles the generated code the native build made; it must not run
# codegen itself (the SDK's rexglue for the target cannot run here, and regenerating
# would rewrite generated/ under the native build). The build-time codegen step stays
# (rexglue.cmake orders the generated sources after it) but runs true instead.
if((CMAKE_CROSSCOMPILING OR FORZA_SKIP_CODEGEN) AND TARGET rex::rexglue)
    # A no-op that takes any arguments; Windows has no /usr/bin/true.
    if(CMAKE_HOST_WIN32)
        set(_codegen_noop "${CMAKE_CURRENT_BINARY_DIR}/codegen_skipped.cmd")
        # Written only when it differs: a rewrite is a new file time, and the custom commands
        # that run the tool depend on it.
        set(_codegen_noop_text "@exit /b 0\r\n")
        set(_codegen_noop_old "")
        if(EXISTS "${_codegen_noop}")
            file(READ "${_codegen_noop}" _codegen_noop_old)
        endif()
        if(NOT _codegen_noop_old STREQUAL _codegen_noop_text)
            file(WRITE "${_codegen_noop}" "${_codegen_noop_text}")
        endif()
    else()
        set(_codegen_noop /usr/bin/true)
    endif()
    set_target_properties(rex::rexglue PROPERTIES
        IMPORTED_LOCATION "${_codegen_noop}" IMPORTED_LOCATION_RELEASE "${_codegen_noop}")
    message(STATUS "Codegen is skipped: compiling generated/ as it is")
elseif(TARGET rex::rexglue AND EXISTS "${FORZA_REXGLUE}")
    get_target_property(_configs rex::rexglue IMPORTED_CONFIGURATIONS)
    set_target_properties(rex::rexglue PROPERTIES IMPORTED_LOCATION "${FORZA_REXGLUE}")
    foreach(_config IN LISTS _configs)
        set_target_properties(rex::rexglue PROPERTIES
            IMPORTED_LOCATION_${_config} "${FORZA_REXGLUE}")
    endforeach()
    # A new tool reruns codegen (its depfile lists only the inputs).
    add_custom_command(OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/${FORZA_GENERATED}/default/codegen.build.stamp"
        APPEND DEPENDS "${FORZA_REXGLUE}")
    message(STATUS "Codegen tool: ${FORZA_REXGLUE}")
elseif(TARGET rex::rexglue)
    message(WARNING "Patched rexglue not found at ${FORZA_REXGLUE}; codegen uses the SDK's, "
                    "whose dot products differ from Xenon's. Run tools/build_rexglue_sdk.sh.")
endif()

# Sources
set(FORZA_SOURCES
    src/main.cpp
    src/debug/audio_level.cpp
    src/debug/cpu_profile.cpp
    src/debug/codriver_log.cpp
    src/debug/dlc_log.cpp
    src/debug/fault_guard.cpp
    src/debug/fiber_trace.cpp
    src/debug/lobby_log.cpp
    src/debug/frame_stats.cpp
    src/debug/thread_trace.cpp
    src/debug/frame_dump.cpp
    src/hooks/compressed_stream_stall.cpp
    src/hooks/crowd_anim.cpp
    src/hooks/garage_camera.cpp
    src/hooks/ultrawide_projection.cpp
    src/hooks/frame_time.cpp
    src/hooks/graphics_menu.cpp
    src/hooks/gpu_wait.cpp
    src/hooks/physics_loader_check.cpp
    src/hooks/resource_data_release.cpp
    src/hooks/thumbnail_sync.cpp
    src/hooks/world_challenge.cpp
    src/hooks/world_drop_in.cpp
    src/hooks/world_events.cpp
    src/kernel/critical_section.cpp
    src/kernel/file_delete_on_close.cpp
    src/kernel/file_size_refresh.cpp
    src/kernel/input_autopress.cpp
    src/kernel/identity.cpp
    src/kernel/live_lsp.cpp
    src/kernel/live_tcp.cpp
    src/kernel/live_friends.cpp
    src/kernel/live_invites.cpp
    src/kernel/live_xmsg.cpp
    src/kernel/module_resident.cpp
    src/kernel/net.cpp
    src/kernel/proc_address_cache.cpp
    src/kernel/xam_enumerate.cpp
    src/kernel/xam_loader.cpp
    src/kernel/xam_nui.cpp
    src/kernel/xam_signin.cpp
    src/kernel/xecrypt_rsa.cpp
    src/kernel/xekeys.cpp
    src/platform/achievement_toast.cpp
    src/platform/ultrawide.cpp
    src/platform/hud_overlay.cpp
    src/platform/motion_blur_fix.cpp
    src/platform/sdk_import.cpp
    src/platform/socket.cpp
    src/platform/vulkan_hooks.cpp
)

# fiber_trace.cpp interposes the SDK's rexcrt_SwitchToFiber with dlsym(RTLD_NEXT): Linux only.
if(WIN32)
    list(REMOVE_ITEM FORZA_SOURCES src/debug/fiber_trace.cpp)
    add_executable(forza WIN32 ${FORZA_SOURCES})
    target_compile_definitions(forza PRIVATE _CRT_SECURE_NO_WARNINGS)
    target_link_libraries(forza PRIVATE ws2_32)
else()
    add_executable(forza ${FORZA_SOURCES})
endif()

rexglue_setup_target(forza GPU_PLUGINS xenos)
target_compile_definitions(forza PRIVATE FORZA_TITLE_UPDATE=${FORZA_TITLE_UPDATE})

# src/platform/vulkan_hooks.cpp (and the app header) include the SDK's Vulkan headers,
# which include <renderdoc_app.h> from this interface target and the X11/Wayland client
# headers (stand-ins in src/platform/wsi_stubs, so no window-system packages are needed).
# From RecompiledHaloReach.
if(TARGET rex::renderdoc)
    target_link_libraries(forza PRIVATE rex::renderdoc)
endif()
if(UNIX AND NOT APPLE)
    set_source_files_properties(src/platform/vulkan_hooks.cpp PROPERTIES
        INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/wsi_stubs")
endif()

# The stock SDK Xenos plugin has rendering bugs (e.g. it reads the texture-fetch
# exponent bias from the wrong fetch-constant word, which darkens textures 256x).
# tools/build_rexglue_sdk.sh builds a patched plugin; this copies it over the SDK
# one that rexglue_setup_target() stages next to the binary.
# This project's overlay first; RecompiledHaloReach's (same patch set so far) otherwise.
set(_forza_plugin "$ENV{HOME}/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64/lib/librexgpu-xenos.so")
if(NOT EXISTS "${_forza_plugin}")
    set(_forza_plugin "$ENV{HOME}/rexglue-sdk-patched/0.10.0.24/linux-amd64/lib/librexgpu-xenos.so")
endif()
set(FORZA_XENOS_PLUGIN "${_forza_plugin}"
    CACHE FILEPATH "Patched librexgpu-xenos.so to ship instead of the SDK's")
if(UNIX AND NOT APPLE)
    if(EXISTS "${FORZA_XENOS_PLUGIN}")
        add_custom_command(TARGET forza POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${FORZA_XENOS_PLUGIN}" "$<TARGET_FILE_DIR:forza>/librexgpu-xenos.so"
            VERBATIM)
    else()
        message(WARNING "Patched GPU plugin not found at ${FORZA_XENOS_PLUGIN}; "
                        "textures will render dark. Run tools/build_rexglue_sdk.sh.")
    endif()
endif()

# The SDK runtime dlopen()s guest-DLL modules by bare target name on Linux
# (no "lib" prefix, no ".so" suffix), so emit the libraries under that name.
if(UNIX AND NOT APPLE)
    foreach(_module forza_XMediaFacade_default forza_SpeechFacade_default)
        if(TARGET ${_module})
            set_target_properties(${_module} PROPERTIES PREFIX "" SUFFIX "")
        endif()
    endforeach()
endif()

# Retain the notice for the adapted ultrawide presentation strategy with the binary.
add_custom_command(TARGET forza POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE-Pinyon-Shift"
        "$<TARGET_FILE_DIR:forza>/LICENSE-Pinyon-Shift"
    VERBATIM)
