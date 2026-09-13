"""Application metadata and the tool registry shared by backend and frontend."""

MAIN_CONTRIBUTOR = "TheLycanFenrir"
VERSION = "1.3.0"
HOME_VIEW_ID = "home"

APP_TITLE = "Lycan Utilities"
APP_SUBTITLE = (
    "Convert media files and generate textures with a single lightweight toolkit."
)
# External repository/profile shown by the header GitHub button and the
# "About" modal. Point this at the exact repository when it is published.
GITHUB_REPOSITORY_URL = "https://github.com/TheLycanFenrir"

# Tool registry used by the home dashboard cards and the backend job runner.
# `icon` is an emoji fallback; `icon_file` is the file inside web/assets/icons.
TOOLS = [
    {
        "id": "frames_to_video",
        "title": "Frames to Video",
        "description": "Turn image sequences into MP4, WebM, GIF, APNG or WEBP videos.",
        "icon": "🎞️",
        "icon_file": "tabs/frames_to_video.png",
        "badge": "Beta",
        "tags": ["video", "convert", "frames", "sequence", "mp4", "webm", "gif", "apng", "webp", "animation"],
    },
    {
        "id": "video_audio_merger",
        "title": "Video Audio Merger",
        "description": "Merge video and audio tracks together into a single file.",
        "icon": "🎵",
        "icon_file": "tabs/video_audio_merger.png",
        "badge": "Coming Soon",
        "tags": ["video", "audio", "merge", "mux", "combine", "track"],
    },
    {
        "id": "image_splitter",
        "title": "Image Splitter",
        "description": "Split large textures into grids, custom tile sizes or alpha components.",
        "icon": "✂️",
        "icon_file": "tabs/image_splitter.png",
        "badge": "Beta",
        "tags": ["image", "texture", "split", "crop", "grid", "tile", "alpha", "resize"],
    },
    {
        "id": "texture_mipmap",
        "title": "Texture Mipmap Generator",
        "description": "Generate mipmap chains for DDS and other texture workflows.",
        "icon": "🧊",
        "icon_file": "tabs/texture_mipmap_generator.png",
        "badge": "Alpha",
        "tags": ["texture", "mipmap", "dds", "generate", "3d", "chain"],
    },
    {
        "id": "image_watermarker",
        "title": "Image Watermarker",
        "description": "Watermark any image",
        "icon_file": "tabs/video_audio_merger.png",
        "icon": "🖼️",
        "badge": "Coming Soon",
        "tags": ["image", "watermark", "overlay", "text", "logo"],
    }
]

# Tools that are placeholders and have no backend job handler yet.
COMING_SOON_TOOLS = {"video_audio_merger"}