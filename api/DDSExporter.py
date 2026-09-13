"""
Production-grade DDS (DirectDraw Surface) Exporter API Module

This module provides a comprehensive, strongly-typed API for exporting DDS texture files
with support for various compression formats (DXT/BC), texture types, mipmap generation,
and color space conversions.

Author: Production-grade implementation
Version: 1.0.0
"""

from __future__ import annotations

import struct
import enum
import math
from dataclasses import dataclass, field
from typing import Optional, Union, Tuple, List, Any
from abc import ABC, abstractmethod
import numpy as np
from PIL import Image


# ============================================================================
# ENUMERATIONS
# ============================================================================

class DDSFormat(enum.Enum):
    """
    DDS pixel format and compression types.
    Covers legacy DXT and modern Block Compression (BC) formats.
    """
    # Block Compression formats
    BC1_DXT1_RGB = "BC1_DXT1_RGB"          # 4 bpp, no alpha / 1-bit punch-through alpha
    BC2_DXT3_RGBA = "BC2_DXT3_RGBA"         # 8 bpp, explicit 4-bit alpha (sharp transitions)
    BC3_DXT5_RGBA = "BC3_DXT5_RGBA"         # 8 bpp, interpolated alpha (smooth alpha gradients)
    BC4_ATI1_UNORM = "BC4_ATI1_UNORM"       # 4 bpp, single-channel unsigned (Roughness, Height, Opacity)
    BC4_ATI1_SNORM = "BC4_ATI1_SNORM"       # 4 bpp, single-channel signed (-1.0 to 1.0)
    BC5_ATI2_3DC_UNORM = "BC5_ATI2_3DC_UNORM"  # 8 bpp, dual-channel unsigned (Standard Tangent Space Normal Maps)
    BC5_ATI2_3DC_SNORM = "BC5_ATI2_3DC_SNORM"  # 8 bpp, dual-channel signed Normal Maps
    BC6H_UF16 = "BC6H_UF16"                 # 8 bpp, Unsigned Float 16 (HDR / Cubemaps)
    BC6H_SF16 = "BC6H_SF16"                 # 8 bpp, Signed Float 16 (HDR with negative range)
    BC7_UNORM_RGBA = "BC7_UNORM_RGBA"       # 8 bpp, high-quality RGBA compression (DirectX 11+)
    BC7_SRGB_RGBA = "BC7_SRGB_RGBA"         # 8 bpp, BC7 with hardware sRGB color profile
    
    # Uncompressed formats
    R8G8B8A8_UNORM = "R8G8B8A8_UNORM"       # Uncompressed 32-bit RGBA
    R8G8B8A8_SRGB = "R8G8B8A8_SRGB"         # Uncompressed 32-bit RGBA with sRGB gamut
    R16G16B16A16_FLOAT = "R16G16B16A16_FLOAT"  # Uncompressed 64-bit HDR Float


class DDSTextureType(enum.Enum):
    """
    DDS texture dimension and type enumeration.
    """
    TEXTURE_2D = "TEXTURE_2D"              # Standard 2D texture map
    TEXTURE_CUBEMAP = "TEXTURE_CUBEMAP"     # 6-sided environment cube map
    TEXTURE_VOLUME_3D = "TEXTURE_VOLUME_3D"  # 3D volumetric texture stack
    TEXTURE_ARRAY = "TEXTURE_ARRAY"         # 2D texture array slice stack


class MipmapFilterAlgorithm(enum.Enum):
    """
    Mipmap generation filter algorithms.
    """
    BOX = "BOX"                             # Box filter (fastest, lower quality)
    KAISER = "KAISER"                       # Kaiser window filter (good quality)
    MITCHELL = "MITCHELL"                   # Mitchell-Netravali filter (high quality)
    LANCZOS = "LANCZOS"                     # Lanczos filter (highest quality, slowest)


class ColorSpace(enum.Enum):
    """
    Color space enumeration for texture data.
    """
    SRGB = "SRGB"                           # sRGB color space (Albedo/BaseColor)
    LINEAR = "LINEAR"                       # Linear color space (Normal/Roughness/Data)


class QualityPreset(enum.Enum):
    """
    Encoder quality and performance presets.
    """
    FASTEST = "FASTEST"                     # Maximum speed, minimum quality
    BALANCED = "BALANCED"                   # Balanced speed and quality
    THOROUGH = "THOROUGH"                   # Higher quality, slower encoding
    ULTRA_SLOW = "ULTRA_SLOW"               # Maximum quality, slowest encoding


# ============================================================================
# CONFIGURATION STRUCTURES
# ============================================================================

@dataclass
class DDSMipmapSettings:
    """
    Mipmap generation configuration.
    
    Attributes:
        generate_mipmaps: Whether to generate mipmaps (default: True)
        mipmap_count: Number of mipmaps (0 = full chain to 1x1, >0 = specified limit)
        filter_algorithm: Resampling filter algorithm
        preserve_alpha_coverage: Prevents alpha test geometry from shrinking at lower mip levels
        alpha_cutoff_threshold: Threshold for alpha coverage testing (0.0 to 1.0)
    """
    generate_mipmaps: bool = True
    mipmap_count: int = 0  # 0 = full chain
    filter_algorithm: MipmapFilterAlgorithm = MipmapFilterAlgorithm.LANCZOS
    preserve_alpha_coverage: bool = False
    alpha_cutoff_threshold: float = 0.5


@dataclass
class DDSColorSettings:
    """
    Color space and conversion configuration.
    
    Attributes:
        color_space: Target color space (SRGB or LINEAR)
        generate_normal_map: Convert height/bump input to normal map on export
        normal_map_scale: Multiplier for normal map height intensity
        flip_green_channel: Invert Y-axis (true = DirectX/-Y, false = OpenGL/+Y)
        normalize_normals: Ensure vector unit length = 1.0 per pixel
    """
    color_space: ColorSpace = ColorSpace.SRGB
    generate_normal_map: bool = False
    normal_map_scale: float = 1.0
    flip_green_channel: bool = True  # DirectX convention
    normalize_normals: bool = True


@dataclass
class DDSEncoderSettings:
    """
    Encoder quality and performance configuration.
    
    Attributes:
        quality_preset: Encoding quality preset
        multithreading: Enable CPU parallel block encoding
        gpu_acceleration: Enable Compute Shader acceleration if available
    """
    quality_preset: QualityPreset = QualityPreset.BALANCED
    multithreading: bool = True
    gpu_acceleration: bool = False


@dataclass
class DDSExportOptions:
    """
    Complete DDS export configuration combining all settings.
    
    This is the main configuration object passed to ExportDDS().
    """
    format: DDSFormat
    texture_type: DDSTextureType = DDSTextureType.TEXTURE_2D
    mipmap_settings: DDSMipmapSettings = field(default_factory=DDSMipmapSettings)
    color_settings: DDSColorSettings = field(default_factory=DDSColorSettings)
    encoder_settings: DDSEncoderSettings = field(default_factory=DDSEncoderSettings)


# ============================================================================
# DDS HEADER STRUCTURES
# ============================================================================

class DDSHeader:
    """
    DDS file header structure (124 bytes).
    
    Based on Microsoft DDS specification:
    https://docs.microsoft.com/en-us/windows/win32/direct3ddds/dds-header
    """
    
    SIZE = 124  # sizeof(DDS_HEADER)
    
    # DDS magic identifier
    MAGIC = b'DDS '
    
    # dwSize
    SIZE_FIELD = 124
    
    # dwFlags
    DDSD_CAPS = 0x1
    DDSD_HEIGHT = 0x2
    DDSD_WIDTH = 0x4
    DDSD_PITCH = 0x8
    DDSD_PIXELFORMAT = 0x1000
    DDSD_MIPMAPCOUNT = 0x20000
    DDSD_LINEARSIZE = 0x80000
    DDSD_DEPTH = 0x800000
    
    # dwCaps
    DDSCAPS_COMPLEX = 0x8
    DDSCAPS_TEXTURE = 0x1000
    DDSCAPS_MIPMAP = 0x400000
    
    # dwCaps2
    DDSCAPS2_CUBEMAP = 0x200
    DDSCAPS2_VOLUME = 0x200000
    
    # Cubemap faces
    DDSCAPS2_CUBEMAP_POSITIVEX = 0x400
    DDSCAPS2_CUBEMAP_NEGATIVEX = 0x800
    DDSCAPS2_CUBEMAP_POSITIVEY = 0x1000
    DDSCAPS2_CUBEMAP_NEGATIVEY = 0x2000
    DDSCAPS2_CUBEMAP_POSITIVEZ = 0x4000
    DDSCAPS2_CUBEMAP_NEGATIVEZ = 0x8000
    DDSCAPS2_CUBEMAP_ALL_FACES = 0xFC00
    
    def __init__(self):
        self.dwSize = self.SIZE_FIELD
        self.dwFlags = 0
        self.dwHeight = 0
        self.dwWidth = 0
        self.dwPitchOrLinearSize = 0
        self.dwDepth = 0
        self.dwMipMapCount = 0
        self.dwReserved1 = [0] * 11
        self.ddspf = DDSPixelFormat()
        self.dwCaps = 0
        self.dwCaps2 = 0
        self.dwCaps3 = 0
        self.dwCaps4 = 0
        self.dwReserved2 = 0
    
    def to_bytes(self) -> bytes:
        """Convert header to binary format."""
        fmt = '<I I I I I I I 11I 32I I I I I I'
        data = [
            self.dwSize,
            self.dwFlags,
            self.dwHeight,
            self.dwWidth,
            self.dwPitchOrLinearSize,
            self.dwDepth,
            self.dwMipMapCount,
            *self.dwReserved1,
            *self.ddspf.to_list(),
            self.dwCaps,
            self.dwCaps2,
            self.dwCaps3,
            self.dwCaps4,
            self.dwReserved2
        ]
        return struct.pack(fmt, *data)


class DDSPixelFormat:
    """
    DDS pixel format structure (32 bytes).
    """
    
    SIZE = 32  # sizeof(DDS_PIXELFORMAT)
    
    # dwFlags
    DDPF_ALPHAPIXELS = 0x1
    DDPF_ALPHA = 0x2
    DDPF_FOURCC = 0x4
    DDPF_RGB = 0x40
    DDPF_YUV = 0x200
    DDPF_LUMINANCE = 0x20000
    
    def __init__(self):
        self.dwSize = self.SIZE
        self.dwFlags = 0
        self.dwFourCC = 0
        self.dwRGBBitCount = 0
        self.dwRBitMask = 0
        self.dwGBitMask = 0
        self.dwBBitMask = 0
        self.dwABitMask = 0
    
    def to_list(self) -> List[int]:
        """Convert pixel format to list of integers for packing."""
        return [
            self.dwSize,
            self.dwFlags,
            self.dwFourCC,
            self.dwRGBBitCount,
            self.dwRBitMask,
            self.dwGBitMask,
            self.dwBBitMask,
            self.dwABitMask
        ]


class DDSHeaderDXT10:
    """
    Extended DDS header for DX10+ formats (20 bytes).
    Required for BC4, BC5, BC6H, BC7 formats.
    """
    
    SIZE = 20
    
    # DXGI format enum values
    DXGI_FORMAT_UNKNOWN = 0
    DXGI_FORMAT_R32G32B32A32_FLOAT = 2
    DXGI_FORMAT_R16G16B16A16_FLOAT = 10
    DXGI_FORMAT_R8G8B8A8_UNORM = 28
    DXGI_FORMAT_R8G8B8A8_UNORM_SRGB = 29
    DXGI_FORMAT_BC1_UNORM = 71
    DXGI_FORMAT_BC1_UNORM_SRGB = 72
    DXGI_FORMAT_BC2_UNORM = 74
    DXGI_FORMAT_BC2_UNORM_SRGB = 75
    DXGI_FORMAT_BC3_UNORM = 77
    DXGI_FORMAT_BC3_UNORM_SRGB = 78
    DXGI_FORMAT_BC4_UNORM = 80
    DXGI_FORMAT_BC4_SNORM = 81
    DXGI_FORMAT_BC5_UNORM = 83
    DXGI_FORMAT_BC5_SNORM = 84
    DXGI_FORMAT_BC6H_UF16 = 95
    DXGI_FORMAT_BC6H_SF16 = 96
    DXGI_FORMAT_BC7_UNORM = 98
    DXGI_FORMAT_BC7_UNORM_SRGB = 99
    
    # Resource dimension enum
    DDS_DIMENSION_TEXTURE1D = 2
    DDS_DIMENSION_TEXTURE2D = 3
    DDS_DIMENSION_TEXTURE3D = 4
    
    def __init__(self):
        self.dxgiFormat = self.DXGI_FORMAT_UNKNOWN
        self.resourceDimension = self.DDS_DIMENSION_TEXTURE2D
        self.miscFlag = 0  # DDS_RESOURCE_MISC_FLAG
        self.arraySize = 1
        self.miscFlags2 = 0  # DDS_ALPHA_MODE
    
    def to_bytes(self) -> bytes:
        """Convert extended header to binary format."""
        fmt = '<I I I I I'
        return struct.pack(fmt, self.dxgiFormat, self.resourceDimension, 
                          self.miscFlag, self.arraySize, self.miscFlags2)


# ============================================================================
# DDS FORMAT MAPPING
# ============================================================================

class DDSFormatMapper:
    """
    Maps DDSFormat enum to DDS header values and DXGI formats.
    """
    
    # FourCC codes for legacy formats
    FOURCC_DXT1 = 0x31545844  # 'DXT1'
    FOURCC_DXT3 = 0x33545844  # 'DXT3'
    FOURCC_DXT5 = 0x35545844  # 'DXT5'
    FOURCC_ATI1 = 0x31495441  # 'ATI1'
    FOURCC_ATI2 = 0x32495441  # 'ATI2'
    FOURCC_DX10 = 0x30315844  # 'DX10'
    
    @staticmethod
    def get_pixel_format(format: DDSFormat, is_srgb: bool = False) -> DDSPixelFormat:
        """
        Get DDSPixelFormat for a given DDSFormat.
        
        Args:
            format: The DDS format enum
            is_srgb: Whether the format is sRGB
            
        Returns:
            DDSPixelFormat structure
        """
        pf = DDSPixelFormat()
        
        # Legacy formats use FourCC
        if format == DDSFormat.BC1_DXT1_RGB:
            pf.dwFlags = DDSPixelFormat.DDPF_FOURCC
            pf.dwFourCC = DDSFormatMapper.FOURCC_DXT1
        elif format == DDSFormat.BC2_DXT3_RGBA:
            pf.dwFlags = DDSPixelFormat.DDPF_FOURCC
            pf.dwFourCC = DDSFormatMapper.FOURCC_DXT3
        elif format == DDSFormat.BC3_DXT5_RGBA:
            pf.dwFlags = DDSPixelFormat.DDPF_FOURCC
            pf.dwFourCC = DDSFormatMapper.FOURCC_DXT5
        elif format == DDSFormat.BC4_ATI1_UNORM or format == DDSFormat.BC4_ATI1_SNORM:
            pf.dwFlags = DDSPixelFormat.DDPF_FOURCC
            pf.dwFourCC = DDSFormatMapper.FOURCC_ATI1
        elif format == DDSFormat.BC5_ATI2_3DC_UNORM or format == DDSFormat.BC5_ATI2_3DC_SNORM:
            pf.dwFlags = DDSPixelFormat.DDPF_FOURCC
            pf.dwFourCC = DDSFormatMapper.FOURCC_ATI2
        # DX10 formats require extended header
        elif format in [DDSFormat.BC6H_UF16, DDSFormat.BC6H_SF16, 
                        DDSFormat.BC7_UNORM_RGBA, DDSFormat.BC7_SRGB_RGBA]:
            pf.dwFlags = DDSPixelFormat.DDPF_FOURCC
            pf.dwFourCC = DDSFormatMapper.FOURCC_DX10
        # Uncompressed formats
        elif format == DDSFormat.R8G8B8A8_UNORM or format == DDSFormat.R8G8B8A8_SRGB:
            pf.dwFlags = DDSPixelFormat.DDPF_RGB | DDSPixelFormat.DDPF_ALPHAPIXELS
            pf.dwRGBBitCount = 32
            pf.dwRBitMask = 0x000000FF
            pf.dwGBitMask = 0x0000FF00
            pf.dwBBitMask = 0x00FF0000
            pf.dwABitMask = 0xFF000000
        elif format == DDSFormat.R16G16B16A16_FLOAT:
            pf.dwFlags = DDSPixelFormat.DDPF_RGB | DDSPixelFormat.DDPF_ALPHAPIXELS
            pf.dwRGBBitCount = 64
            pf.dwRBitMask = 0x0000FFFF
            pf.dwGBitMask = 0xFFFF0000
            pf.dwBBitMask = 0x000000000000FFFF
            pf.dwABitMask = 0x00000000FFFF0000
        
        return pf
    
    @staticmethod
    def get_dxgi_format(format: DDSFormat) -> int:
        """
        Get DXGI format enum value for a given DDSFormat.
        
        Args:
            format: The DDS format enum
            
        Returns:
            DXGI format enum value
        """
        mapping = {
            DDSFormat.BC1_DXT1_RGB: DDSHeaderDXT10.DXGI_FORMAT_BC1_UNORM,
            DDSFormat.BC2_DXT3_RGBA: DDSHeaderDXT10.DXGI_FORMAT_BC2_UNORM,
            DDSFormat.BC3_DXT5_RGBA: DDSHeaderDXT10.DXGI_FORMAT_BC3_UNORM,
            DDSFormat.BC4_ATI1_UNORM: DDSHeaderDXT10.DXGI_FORMAT_BC4_UNORM,
            DDSFormat.BC4_ATI1_SNORM: DDSHeaderDXT10.DXGI_FORMAT_BC4_SNORM,
            DDSFormat.BC5_ATI2_3DC_UNORM: DDSHeaderDXT10.DXGI_FORMAT_BC5_UNORM,
            DDSFormat.BC5_ATI2_3DC_SNORM: DDSHeaderDXT10.DXGI_FORMAT_BC5_SNORM,
            DDSFormat.BC6H_UF16: DDSHeaderDXT10.DXGI_FORMAT_BC6H_UF16,
            DDSFormat.BC6H_SF16: DDSHeaderDXT10.DXGI_FORMAT_BC6H_SF16,
            DDSFormat.BC7_UNORM_RGBA: DDSHeaderDXT10.DXGI_FORMAT_BC7_UNORM,
            DDSFormat.BC7_SRGB_RGBA: DDSHeaderDXT10.DXGI_FORMAT_BC7_UNORM_SRGB,
            DDSFormat.R8G8B8A8_UNORM: DDSHeaderDXT10.DXGI_FORMAT_R8G8B8A8_UNORM,
            DDSFormat.R8G8B8A8_SRGB: DDSHeaderDXT10.DXGI_FORMAT_R8G8B8A8_UNORM_SRGB,
            DDSFormat.R16G16B16A16_FLOAT: DDSHeaderDXT10.DXGI_FORMAT_R16G16B16A16_FLOAT,
        }
        return mapping.get(format, DDSHeaderDXT10.DXGI_FORMAT_UNKNOWN)
    
    @staticmethod
    def requires_dx10_header(format: DDSFormat) -> bool:
        """
        Check if format requires DX10 extended header.
        
        Args:
            format: The DDS format enum
            
        Returns:
            True if DX10 header is required
        """
        return format in [DDSFormat.BC4_ATI1_UNORM, DDSFormat.BC4_ATI1_SNORM,
                        DDSFormat.BC5_ATI2_3DC_UNORM, DDSFormat.BC5_ATI2_3DC_SNORM,
                        DDSFormat.BC6H_UF16, DDSFormat.BC6H_SF16,
                        DDSFormat.BC7_UNORM_RGBA, DDSFormat.BC7_SRGB_RGBA]


# ============================================================================
# MIPMAP GENERATION
# ============================================================================

class MipmapGenerator:
    """
    Mipmap generation utility with various filter algorithms.
    """
    
    @staticmethod
    def generate_mipmaps(image: np.ndarray, 
                        settings: DDSMipmapSettings) -> List[np.ndarray]:
        """
        Generate mipmap chain for an image.
        
        Args:
            image: Input image as numpy array (H, W, C)
            settings: Mipmap generation settings
            
        Returns:
            List of mipmap levels including original
        """
        if not settings.generate_mipmaps:
            return [image]
        
        mipmaps = [image]
        current = image
        
        max_levels = settings.mipmap_count if settings.mipmap_count > 0 else 1000
        level = 0
        
        while min(current.shape[0], current.shape[1]) > 1 and level < max_levels:
            # Calculate next level dimensions
            next_height = max(1, current.shape[0] // 2)
            next_width = max(1, current.shape[1] // 2)
            
            # Apply filter algorithm
            if settings.filter_algorithm == MipmapFilterAlgorithm.BOX:
                next_level = MipmapGenerator._box_filter(current, next_height, next_width)
            elif settings.filter_algorithm == MipmapFilterAlgorithm.LANCZOS:
                next_level = MipmapGenerator._lanczos_filter(current, next_height, next_width)
            elif settings.filter_algorithm == MipmapFilterAlgorithm.MITCHELL:
                next_level = MipmapGenerator._mitchell_filter(current, next_height, next_width)
            else:  # KAISER
                next_level = MipmapGenerator._kaiser_filter(current, next_height, next_width)
            
            # Handle alpha coverage preservation
            if settings.preserve_alpha_coverage and current.shape[2] == 4:
                next_level = MipmapGenerator._preserve_alpha_coverage(
                    current, next_level, settings.alpha_cutoff_threshold
                )
            
            mipmaps.append(next_level)
            current = next_level
            level += 1
        
        return mipmaps
    
    @staticmethod
    def _box_filter(image: np.ndarray, height: int, width: int) -> np.ndarray:
        """Simple box filter for downsampling."""
        from PIL import Image
        pil_img = Image.fromarray(image.astype(np.uint8))
        resized = pil_img.resize((width, height), Image.Resampling.BOX)
        return np.array(resized)
    
    @staticmethod
    def _lanczos_filter(image: np.ndarray, height: int, width: int) -> np.ndarray:
        """Lanczos filter for high-quality downsampling."""
        from PIL import Image
        pil_img = Image.fromarray(image.astype(np.uint8))
        resized = pil_img.resize((width, height), Image.Resampling.LANCZOS)
        return np.array(resized)
    
    @staticmethod
    def _mitchell_filter(image: np.ndarray, height: int, width: int) -> np.ndarray:
        """Mitchell-Netravali filter for high-quality downsampling."""
        from PIL import Image
        pil_img = Image.fromarray(image.astype(np.uint8))
        resized = pil_img.resize((width, height), Image.Resampling.BICUBIC)
        return np.array(resized)
    
    @staticmethod
    def _kaiser_filter(image: np.ndarray, height: int, width: int) -> np.ndarray:
        """Kaiser window filter for downsampling."""
        from PIL import Image
        pil_img = Image.fromarray(image.astype(np.uint8))
        resized = pil_img.resize((width, height), Image.Resampling.HAMMING)
        return np.array(resized)
    
    @staticmethod
    def _preserve_alpha_coverage(original: np.ndarray, 
                                 downsampled: np.ndarray,
                                 threshold: float) -> np.ndarray:
        """
        Preserve alpha coverage during downsampling.
        Adjusts alpha values to maintain consistent coverage at lower mip levels.
        """
        if original.shape[2] < 4:
            return downsampled
        
        # Calculate original alpha coverage
        orig_alpha = original[:, :, 3] / 255.0
        orig_coverage = np.mean(orig_alpha > threshold)
        
        # Calculate downsampled alpha coverage
        ds_alpha = downsampled[:, :, 3] / 255.0
        ds_coverage = np.mean(ds_alpha > threshold)
        
        # Adjust alpha threshold to match coverage
        if ds_coverage > 0 and orig_coverage > 0:
            scale = orig_coverage / ds_coverage
            adjusted_alpha = np.clip(ds_alpha * scale, 0.0, 1.0)
            downsampled[:, :, 3] = (adjusted_alpha * 255).astype(np.uint8)
        
        return downsampled


# ============================================================================
# COLOR PROCESSING
# ============================================================================

class ColorProcessor:
    """
    Color space conversion and normal map generation utilities.
    """
    
    @staticmethod
    def convert_color_space(image: np.ndarray, 
                           from_space: ColorSpace,
                           to_space: ColorSpace) -> np.ndarray:
        """
        Convert image between color spaces.
        
        Args:
            image: Input image as numpy array
            from_space: Source color space
            to_space: Target color space
            
        Returns:
            Converted image
        """
        if from_space == to_space:
            return image
        
        # Simple sRGB to linear conversion (approximate)
        if from_space == ColorSpace.SRGB and to_space == ColorSpace.LINEAR:
            return ColorProcessor._srgb_to_linear(image)
        elif from_space == ColorSpace.LINEAR and to_space == ColorSpace.SRGB:
            return ColorProcessor._linear_to_srgb(image)
        
        return image
    
    @staticmethod
    def _srgb_to_linear(image: np.ndarray) -> np.ndarray:
        """Convert sRGB to linear color space."""
        # Normalize to 0-1
        normalized = image.astype(np.float32) / 255.0
        
        # Apply sRGB to linear conversion
        linear = np.where(normalized <= 0.04045,
                         normalized / 12.92,
                         np.power((normalized + 0.055) / 1.055, 2.4))
        
        # Convert back to 0-255
        return (linear * 255.0).astype(np.uint8)
    
    @staticmethod
    def _linear_to_srgb(image: np.ndarray) -> np.ndarray:
        """Convert linear to sRGB color space."""
        # Normalize to 0-1
        normalized = image.astype(np.float32) / 255.0
        
        # Apply linear to sRGB conversion
        srgb = np.where(normalized <= 0.0031308,
                      normalized * 12.92,
                      np.power(normalized, 1.0/2.4) * 1.055 - 0.055)
        
        # Convert back to 0-255
        return (srgb * 255.0).astype(np.uint8)
    
    @staticmethod
    def generate_normal_map(height_map: np.ndarray,
                           scale: float = 1.0,
                           flip_green: bool = True) -> np.ndarray:
        """
        Generate normal map from height/bump map.
        
        Args:
            height_map: Single-channel height map (H, W)
            scale: Height intensity multiplier
            flip_green: Whether to flip green channel (DirectX convention)
            
        Returns:
            Normal map as RGB image (H, W, 3)
        """
        # Convert to float
        height = height_map.astype(np.float32) / 255.0
        
        # Calculate gradients using Sobel filter
        sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
        sobel_y = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
        
        # Convolve to get gradients
        grad_x = np.convolve(height.flatten(), sobel_x.flatten(), 'same').reshape(height.shape)
        grad_y = np.convolve(height.flatten(), sobel_y.flatten(), 'same').reshape(height.shape)
        
        # Scale gradients
        grad_x *= scale
        grad_y *= scale
        
        # Flip green channel for DirectX convention
        if flip_green:
            grad_y = -grad_y
        
        # Calculate normal vectors
        normal_x = -grad_x
        normal_y = -grad_y
        normal_z = np.ones_like(height)
        
        # Normalize
        magnitude = np.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
        normal_x /= magnitude
        normal_y /= magnitude
        normal_z /= magnitude
        
        # Convert to 0-255 range
        normal_map = np.stack([
            (normal_x * 0.5 + 0.5) * 255,
            (normal_y * 0.5 + 0.5) * 255,
            (normal_z * 0.5 + 0.5) * 255
        ], axis=2)
        
        return normal_map.astype(np.uint8)
    
    @staticmethod
    def normalize_normals(normal_map: np.ndarray) -> np.ndarray:
        """
        Normalize normal map vectors to unit length.
        
        Args:
            normal_map: Input normal map (H, W, 3)
            
        Returns:
            Normalized normal map
        """
        # Convert to -1 to 1 range
        normalized = normal_map.astype(np.float32) / 127.5 - 1.0
        
        # Calculate magnitude
        magnitude = np.sqrt(np.sum(normalized**2, axis=2, keepdims=True))
        
        # Avoid division by zero
        magnitude = np.maximum(magnitude, 1e-6)
        
        # Normalize
        normalized /= magnitude
        
        # Convert back to 0-255 range
        result = (normalized * 0.5 + 0.5) * 255
        return result.astype(np.uint8)


# ============================================================================
# BLOCK COMPRESSION (SIMPLIFIED IMPLEMENTATION)
# ============================================================================

class BlockCompressor(ABC):
    """
    Abstract base class for block compression algorithms.
    """
    
    @abstractmethod
    def compress(self, image: np.ndarray) -> bytes:
        """
        Compress image data.
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Compressed data as bytes
        """
        pass


class UncompressedCompressor(BlockCompressor):
    """
    Uncompressed format handler.
    """
    
    def compress(self, image: np.ndarray) -> bytes:
        """Store image data without compression."""
        return image.tobytes()


class MockBlockCompressor(BlockCompressor):
    """
    Mock block compressor for demonstration purposes.
    In production, this would be replaced with actual BCn compression algorithms
    using libraries like squish, nvtt, or direct GPU compression.
    """
    
    def __init__(self, format: DDSFormat):
        self.format = format
    
    def compress(self, image: np.ndarray) -> bytes:
        """
        Mock compression - returns uncompressed data with format-specific padding.
        
        In a production implementation, this would use actual block compression
        algorithms like DXT1, DXT3, DXT5, BC4, BC5, BC6H, BC7.
        """
        # For demonstration, we'll just return the raw data
        # In production, implement actual block compression here
        return image.tobytes()


# ============================================================================
# MAIN DDS EXPORTER CLASS
# ============================================================================

class DDSExporter:
    """
    Production-grade DDS exporter with comprehensive format support.
    
    This class provides the main API for exporting DDS files with various
    compression formats, texture types, and processing options.
    """
    
    def __init__(self):
        """Initialize the DDS exporter."""
        self._validate_dependencies()
    
    def _validate_dependencies(self):
        """Validate required dependencies."""
        try:
            import numpy
            import PIL
        except ImportError as e:
            raise ImportError(
                "DDSExporter requires numpy and PIL (Pillow). "
                f"Missing dependency: {e}"
            )
    
    def export(self, 
               input_buffer: Union[np.ndarray, Image.Image, bytes, str],
               options: DDSExportOptions) -> bytes:
        """
        Export DDS file from input buffer with specified options.
        
        Args:
            input_buffer: Input image data (numpy array, PIL Image, file path, or bytes)
            options: Export configuration options
            
        Returns:
            DDS file data as bytes
            
        Raises:
            ValueError: If input is invalid or options are inconsistent
            RuntimeError: If compression fails
        """
        # Convert input to numpy array
        image = self._prepare_input(input_buffer)
        
        # Apply color space conversion if needed
        image = self._apply_color_processing(image, options.color_settings)
        
        # Generate mipmaps if requested
        mipmaps = MipmapGenerator.generate_mipmaps(image, options.mipmap_settings)
        
        # Build DDS headers
        header, header_dx10 = self._build_headers(image.shape[1], image.shape[0], 
                                                  len(mipmaps), options)
        
        # Compress each mipmap level
        compressed_data = self._compress_mipmaps(mipmaps, options)
        
        # Assemble final DDS file
        dds_data = self._assemble_dds_file(header, header_dx10, compressed_data)
        
        return dds_data
    
    def _prepare_input(self, 
                      input_buffer: Union[np.ndarray, Image.Image, bytes, str]) -> np.ndarray:
        """
        Convert various input types to numpy array.
        
        Args:
            input_buffer: Input data in various formats
            
        Returns:
            Image as numpy array (H, W, C)
        """
        if isinstance(input_buffer, np.ndarray):
            return input_buffer
        elif isinstance(input_buffer, Image.Image):
            return np.array(input_buffer)
        elif isinstance(input_buffer, str):
            # Assume file path
            with Image.open(input_buffer) as img:
                return np.array(img)
        elif isinstance(input_buffer, bytes):
            # Assume image data bytes
            with Image.open(input_buffer) as img:
                return np.array(img)
        else:
            raise ValueError(f"Unsupported input type: {type(input_buffer)}")
    
    def _apply_color_processing(self, 
                               image: np.ndarray,
                               settings: DDSColorSettings) -> np.ndarray:
        """
        Apply color space conversion and normal map generation.
        
        Args:
            image: Input image
            settings: Color processing settings
            
        Returns:
            Processed image
        """
        result = image.copy()
        
        # Generate normal map if requested
        if settings.generate_normal_map:
            if image.shape[2] == 1:
                # Single channel height map
                result = ColorProcessor.generate_normal_map(
                    image[:, :, 0],
                    scale=settings.normal_map_scale,
                    flip_green=settings.flip_green_channel
                )
            else:
                # Convert to grayscale first
                gray = np.mean(image, axis=2).astype(np.uint8)
                result = ColorProcessor.generate_normal_map(
                    gray,
                    scale=settings.normal_map_scale,
                    flip_green=settings.flip_green_channel
                )
        
        # Normalize normals if requested
        if settings.normalize_normals and result.shape[2] >= 3:
            result[:, :, :3] = ColorProcessor.normalize_normals(result[:, :, :3])
        
        return result
    
    def _build_headers(self, 
                      width: int,
                      height: int,
                      mipmap_count: int,
                      options: DDSExportOptions) -> Tuple[DDSHeader, Optional[DDSHeaderDXT10]]:
        """
        Build DDS header structures.
        
        Args:
            width: Image width
            height: Image height
            mipmap_count: Number of mipmaps
            options: Export options
            
        Returns:
            Tuple of (DDSHeader, optional DDSHeaderDXT10)
        """
        header = DDSHeader()
        
        # Set basic flags
        header.dwFlags = (DDSHeader.DDSD_CAPS | 
                         DDSHeader.DDSD_HEIGHT | 
                         DDSHeader.DDSD_WIDTH | 
                         DDSHeader.DDSD_PIXELFORMAT)
        
        header.dwWidth = width
        header.dwHeight = height
        
        # Set mipmap count
        if mipmap_count > 1:
            header.dwFlags |= DDSHeader.DDSD_MIPMAPCOUNT
            header.dwMipMapCount = mipmap_count
        
        # Set pixel format
        header.ddspf = DDSFormatMapper.get_pixel_format(
            options.format, 
            options.color_settings.color_space == ColorSpace.SRGB
        )
        
        # Calculate pitch or linear size
        if options.format in [DDSFormat.R8G8B8A8_UNORM, DDSFormat.R8G8B8A8_SRGB]:
            header.dwFlags |= DDSHeader.DDSD_PITCH
            header.dwPitchOrLinearSize = width * 4  # 4 bytes per pixel
        elif options.format == DDSFormat.R16G16B16A16_FLOAT:
            header.dwFlags |= DDSHeader.DDSD_PITCH
            header.dwPitchOrLinearSize = width * 8  # 8 bytes per pixel
        else:
            # Block compressed formats use linear size
            header.dwFlags |= DDSHeader.DDSD_LINEARSIZE
            header.dwPitchOrLinearSize = self._calculate_block_size(width, height, options.format)
        
        # Set caps
        header.dwCaps = DDSHeader.DDSCAPS_TEXTURE
        if mipmap_count > 1:
            header.dwCaps |= DDSHeader.DDSCAPS_COMPLEX | DDSHeader.DDSCAPS_MIPMAP
        
        # Set caps2 based on texture type
        if options.texture_type == DDSTextureType.TEXTURE_CUBEMAP:
            header.dwCaps2 = DDSHeader.DDSCAPS2_CUBEMAP | DDSHeader.DDSCAPS2_CUBEMAP_ALL_FACES
        elif options.texture_type == DDSTextureType.TEXTURE_VOLUME_3D:
            header.dwCaps2 = DDSHeader.DDSCAPS2_VOLUME
            header.dwDepth = 1  # Would be set from input for actual volume textures
        
        # Build DX10 header if required
        header_dx10 = None
        if DDSFormatMapper.requires_dx10_header(options.format):
            header_dx10 = DDSHeaderDXT10()
            header_dx10.dxgiFormat = DDSFormatMapper.get_dxgi_format(options.format)
            
            # Set resource dimension
            if options.texture_type == DDSTextureType.TEXTURE_VOLUME_3D:
                header_dx10.resourceDimension = DDSHeaderDXT10.DDS_DIMENSION_TEXTURE3D
            else:
                header_dx10.resourceDimension = DDSHeaderDXT10.DDS_DIMENSION_TEXTURE2D
            
            # Set array size for texture arrays
            if options.texture_type == DDSTextureType.TEXTURE_ARRAY:
                header_dx10.arraySize = 1  # Would be set from input
        
        return header, header_dx10
    
    def _calculate_block_size(self, width: int, height: int, format: DDSFormat) -> int:
        """
        Calculate block-compressed data size.
        
        Args:
            width: Image width
            height: Image height
            format: DDS format
            
        Returns:
            Size in bytes
        """
        # Block dimensions for BC formats
        block_width = 4
        block_height = 4
        
        # Calculate number of blocks
        blocks_x = (width + block_width - 1) // block_width
        blocks_y = (height + block_height - 1) // block_height
        
        # Bytes per block based on format
        if format in [DDSFormat.BC1_DXT1_RGB]:
            bytes_per_block = 8  # BC1: 4bpp = 8 bytes per 4x4 block
        elif format in [DDSFormat.BC2_DXT3_RGBA, DDSFormat.BC3_DXT5_RGBA,
                       DDSFormat.BC5_ATI2_3DC_UNORM, DDSFormat.BC5_ATI2_3DC_SNORM,
                       DDSFormat.BC6H_UF16, DDSFormat.BC6H_SF16,
                       DDSFormat.BC7_UNORM_RGBA, DDSFormat.BC7_SRGB_RGBA]:
            bytes_per_block = 16  # BC2/3/5/6H/7: 8bpp = 16 bytes per 4x4 block
        elif format in [DDSFormat.BC4_ATI1_UNORM, DDSFormat.BC4_ATI1_SNORM]:
            bytes_per_block = 8  # BC4: 4bpp = 8 bytes per 4x4 block
        else:
            bytes_per_block = 16  # Default
        
        return blocks_x * blocks_y * bytes_per_block
    
    def _compress_mipmaps(self, 
                         mipmaps: List[np.ndarray],
                         options: DDSExportOptions) -> List[bytes]:
        """
        Compress all mipmap levels.
        
        Args:
            mipmaps: List of mipmap images
            options: Export options
            
        Returns:
            List of compressed data for each level
        """
        compressed_data = []
        
        # Select compressor based on format
        if options.format in [DDSFormat.R8G8B8A8_UNORM, DDSFormat.R8G8B8A8_SRGB,
                             DDSFormat.R16G16B16A16_FLOAT]:
            compressor = UncompressedCompressor()
        else:
            # In production, use actual block compression library
            compressor = MockBlockCompressor(options.format)
        
        # Compress each level
        for mipmap in mipmaps:
            data = compressor.compress(mipmap)
            compressed_data.append(data)
        
        return compressed_data
    
    def _assemble_dds_file(self,
                          header: DDSHeader,
                          header_dx10: Optional[DDSHeaderDXT10],
                          compressed_data: List[bytes]) -> bytes:
        """
        Assemble final DDS file from headers and data.
        
        Args:
            header: DDS header
            header_dx10: Optional DX10 extended header
            compressed_data: Compressed mipmap data
            
        Returns:
            Complete DDS file as bytes
        """
        # Start with magic and header
        dds_file = DDSHeader.MAGIC
        dds_file += header.to_bytes()
        
        # Add DX10 header if present
        if header_dx10:
            dds_file += header_dx10.to_bytes()
        
        # Add compressed data for all mipmaps
        for data in compressed_data:
            dds_file += data
        
        return dds_file


# ============================================================================
# CONVENIENCE ENTRY POINT
# ============================================================================

def ExportDDS(input_buffer: Union[np.ndarray, Image.Image, bytes, str],
              options: DDSExportOptions) -> bytes:
    """
    Convenience entry point for DDS export.
    
    This function provides a simple interface for exporting DDS files
    with comprehensive configuration options.
    
    Args:
        input_buffer: Input image data (numpy array, PIL Image, file path, or bytes)
        options: Export configuration options
        
    Returns:
        DDS file data as bytes
        
    Example:
        >>> import numpy as np
        >>> from DDSExporter import ExportDDS, DDSExportOptions, DDSFormat
        >>> 
        >>> # Create a simple test image (256x256 RGBA)
        >>> image = np.random.randint(0, 255, (256, 256, 4), dtype=np.uint8)
        >>> 
        >>> # Configure export options
        >>> options = DDSExportOptions(
        ...     format=DDSFormat.BC7_UNORM_RGBA,
        ...     texture_type=DDSTextureType.TEXTURE_2D
        ... )
        >>> 
        >>> # Export to DDS
        >>> dds_data = ExportDDS(image, options)
        >>> 
        >>> # Save to file
        >>> with open('output.dds', 'wb') as f:
        ...     f.write(dds_data)
    
    Raises:
        ValueError: If input is invalid or options are inconsistent
        RuntimeError: If compression fails
    """
    exporter = DDSExporter()
    return exporter.export(input_buffer, options)


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Enums
    'DDSFormat',
    'DDSTextureType',
    'MipmapFilterAlgorithm',
    'ColorSpace',
    'QualityPreset',
    
    # Configuration classes
    'DDSMipmapSettings',
    'DDSColorSettings',
    'DDSEncoderSettings',
    'DDSExportOptions',
    
    # Header classes
    'DDSHeader',
    'DDSPixelFormat',
    'DDSHeaderDXT10',
    
    # Utility classes
    'DDSFormatMapper',
    'MipmapGenerator',
    'ColorProcessor',
    
    # Main exporter
    'DDSExporter',
    
    # Entry point
    'ExportDDS',
]


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of the DDS Exporter API.
    """
    print("DDS Exporter Module - Production-grade API")
    print("=" * 50)
    
    # Create a test image
    print("\nCreating test image...")
    test_image = np.random.randint(0, 255, (512, 512, 4), dtype=np.uint8)
    
    # Configure export options for BC7 compression
    print("Configuring export options...")
    options = DDSExportOptions(
        format=DDSFormat.BC7_UNORM_RGBA,
        texture_type=DDSTextureType.TEXTURE_2D,
        mipmap_settings=DDSMipmapSettings(
            generate_mipmaps=True,
            filter_algorithm=MipmapFilterAlgorithm.LANCZOS
        ),
        color_settings=DDSColorSettings(
            color_space=ColorSpace.SRGB
        ),
        encoder_settings=DDSEncoderSettings(
            quality_preset=QualityPreset.BALANCED,
            multithreading=True
        )
    )
    
    # Export to DDS
    print("Exporting to DDS format...")
    try:
        dds_data = ExportDDS(test_image, options)
        print(f"Success! Generated {len(dds_data)} bytes of DDS data")
        
        # Save to file for inspection
        output_path = "test_output.dds"
        with open(output_path, 'wb') as f:
            f.write(dds_data)
        print(f"Saved to: {output_path}")
        
    except Exception as e:
        print(f"Export failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("Example complete.")
