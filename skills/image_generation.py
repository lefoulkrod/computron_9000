"""Image generation skill — image creation and analysis."""

from textwrap import dedent

from sdk.skills import Skill
from tools.generation import generate_image
from tools.virtual_computer.describe_image import describe_image

_SKILL = Skill(
    name="image_generation",
    description="Generate images from text prompts and analyze existing images",
    prompt=dedent("""\
        Image generation and analysis.

        generate_image(description, model, size) — creates images from text
        prompts and delivers them to the UI automatically.
        - description: text prompt describing the image
        - model: "fast" (default), "quality" (best results),
          "photorealistic" (realistic photos)
        - size: "square" (default), "portrait" (tall), "landscape", "wide"

        describe_image(path, prompt) — analyzes an image file and returns a
        text description. Works with PNG, JPEG, GIF, WebP, BMP, TIFF.
    """),
    tools=[
        generate_image,
        describe_image,
    ],
)
