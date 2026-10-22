##
#  Copyright (c) 2011 - 2022, ARM Limited. All rights reserved.
#  Copyright (c) 2014, Linaro Limited. All rights reserved.
#  Copyright (c) 2015 - 2020, Intel Corporation. All rights reserved.
#  Copyright (c) 2018, Bingxing Wang. All rights reserved.
#  Copyright (c) Microsoft Corporation.
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
##

################################################################################
#
# Defines Section - statements that will be processed to create a Makefile.
#
################################################################################
[Defines]
  PLATFORM_NAME                  = cupid
  PLATFORM_GUID                  = 89943F91-0E94-407C-B6B1-545EB4B6BC76
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/cupidPkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = cupidPkg/cupid.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 0

!include WaipioPkg/WaipioPkg.dsc.inc

[PcdsFixedAtBuild]
  #
  # DDR Memory
  #
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000

  #
  # UEFI Stack
  #
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0xA760D000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  #
  # SMBIOS
  #
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"Xiaomi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Xiaomi 12"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"cupid"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"Xiaomi_12_cupid"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"Xiaomi 12"

  #
  # Simple Frame Buffer
  #
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|1080
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|2400
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32

  #
  # Platform PEI
  #
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|cupidPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|cupidPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf


[BuildOptions]
  *_*_AARCH64_CC_FLAGS = -DXNU_PAYLOAD_BASE=0xF6000000ULL -DXNU_RAM_DIAGNOSTICS=1 -DCUPID_EARLY_DIAGNOSTICS=1 -DCUPID_STOCK_FVLIST=1
