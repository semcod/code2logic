#!/usr/bin/env python3
"""
Mermaid to PNG Generator
Converts Mermaid diagrams (.mmd files) to PNG images using various renderers.
"""

import os
import sys
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path


class MermaidRenderer:
    """Base class for Mermaid renderers."""

    def render(self, mmd_file: Path, output_file: Path) -> bool:
        """Render Mermaid file to PNG."""
        raise NotImplementedError


class MermaidCLIRenderer(MermaidRenderer):
    """Render using @mermaid-js/mermaid-cli (npx)."""

    def render(self, mmd_file: Path, output_file: Path) -> bool:
        """Render using mermaid-cli."""
        try:
            cmd = [
                "npx",
                "-y",
                "@mermaid-js/mermaid-cli",
                str(mmd_file),
                "--output",
                str(output_file.parent),
                "--format",
                "png",
                "--backgroundColor",
                "white",
                "--theme",
                "default",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                # mermaid-cli creates file with original name + .png
                expected_output = output_file.parent / f"{mmd_file.stem}.png"
                if expected_output.exists() and expected_output != output_file:
                    shutil.move(str(expected_output), str(output_file))
                return True
            else:
                print(f"Mermaid CLI error: {result.stderr}")
                return False

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"Mermaid CLI not available or timed out: {e}")
            return False


class MermaidInkRenderer(MermaidRenderer):
    """Render using mmdc (mermaid-cli)."""

    def render(self, mmd_file: Path, output_file: Path) -> bool:
        """Render using mmdc command."""
        try:
            cmd = [
                "mmdc",
                "-i",
                str(mmd_file),
                "-o",
                str(output_file),
                "-t",
                "default",
                "-b",
                "white",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return True
            else:
                print(f"mmdc error: {result.stderr}")
                return False

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"mmdc not available or timed out: {e}")
            return False


class PuppeteerRenderer(MermaidRenderer):
    """Render using Puppeteer with HTML template."""

    def render(self, mmd_file: Path, output_file: Path) -> bool:
        """Render using Puppeteer."""
        try:
            # Read Mermaid content
            mmd_content = mmd_file.read_text(encoding="utf-8")

            # Create HTML template
            html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{ margin: 0; padding: 20px; background: white; }}
        .mermaid {{ font-family: Arial, sans-serif; }}
    </style>
</head>
<body>
    <div class="mermaid">
{mmd_content}
    </div>
    <script>
        mermaid.initialize({{ startOnLoad: true }});
    </script>
</body>
</html>
"""

            # Create temporary HTML file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False
            ) as tmp_html:
                tmp_html.write(html_template)
                tmp_html_path = tmp_html.name

            try:
                # Use puppeteer to screenshot
                cmd = [
                    "npx",
                    "-y",
                    "puppeteer",
                    "screenshot",
                    "--url",
                    f"file://{tmp_html_path}",
                    "--output",
                    str(output_file),
                    "--wait-for",
                    ".mermaid",
                    "--full-page",
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                if result.returncode == 0:
                    return True
                else:
                    print(f"Puppeteer error: {result.stderr}")
                    return False

            finally:
                os.unlink(tmp_html_path)

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"Puppeteer not available or timed out: {e}")
            return False


class MermaidGenerator:
    """Main generator class."""

    def __init__(self):
        self.renderers = [
            MermaidCLIRenderer(),
            MermaidInkRenderer(),
            PuppeteerRenderer(),
        ]

    def generate(self, mmd_file: Path, output_file: Path) -> bool:
        """Generate PNG from Mermaid file."""
        if not mmd_file.exists():
            print(f"Error: Mermaid file not found: {mmd_file}")
            return False

        # Create output directory
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Try each renderer
        for renderer in self.renderers:
            print(f"Trying {renderer.__class__.__name__}...")
            if renderer.render(mmd_file, output_file):
                print(f"✓ Generated: {output_file}")
                return True

        print("❌ No renderer available. Install one of:")
        print("  - npm install -g @mermaid-js/mermaid-cli")
        print("  - npm install -g @mermaid-js/mermaid-cli (mmdc)")
        print("  - npm install -g puppeteer")
        return False

    def generate_batch(self, input_dir: Path, output_dir: Path) -> int:
        """Generate PNGs for all .mmd files in directory."""
        mmd_files = list(input_dir.glob("*.mmd"))

        if not mmd_files:
            print(f"No .mmd files found in: {input_dir}")
            return 0

        print(f"Found {len(mmd_files)} Mermaid files")

        success_count = 0
        for mmd_file in mmd_files:
            output_file = output_dir / f"{mmd_file.stem}.png"
            if self.generate(mmd_file, output_file):
                success_count += 1

        print(f"Generated {success_count}/{len(mmd_files)} PNG files")
        return success_count


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate PNG images from Mermaid diagrams",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s flow.mmd flow.png
  %(prog)s flow.mmd                    # Auto-named output
  %(prog)s *.mmd                       # Batch convert
  %(prog)s --batch ./diagrams ./images # Directory batch
        """,
    )

    parser.add_argument("input", help="Input .mmd file or directory")

    parser.add_argument("output", nargs="?", help="Output PNG file or directory")

    parser.add_argument(
        "--batch", action="store_true", help="Batch convert all .mmd files in directory"
    )

    parser.add_argument(
        "--renderer",
        choices=["cli", "mmdc", "puppeteer"],
        help="Force specific renderer",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    generator = MermaidGenerator()

    # Filter renderers if specified
    if args.renderer:
        if args.renderer == "cli":
            generator.renderers = [MermaidCLIRenderer()]
        elif args.renderer == "mmdc":
            generator.renderers = [MermaidInkRenderer()]
        elif args.renderer == "puppeteer":
            generator.renderers = [PuppeteerRenderer()]

    input_path = Path(args.input)

    if args.batch:
        # Batch mode
        output_path = Path(args.output) if args.output else input_path
        success = generator.generate_batch(input_path, output_path)
        sys.exit(0 if success > 0 else 1)

    elif input_path.is_dir():
        # Directory mode - treat as batch
        output_path = Path(args.output) if args.output else input_path
        success = generator.generate_batch(input_path, output_path)
        sys.exit(0 if success > 0 else 1)

    elif input_path.is_file() and input_path.suffix == ".mmd":
        # Single file mode
        if args.output:
            output_path = Path(args.output)
            if output_path.is_dir():
                output_path = output_path / f"{input_path.stem}.png"
        else:
            output_path = input_path.parent / f"{input_path.stem}.png"

        success = generator.generate(input_path, output_path)
        sys.exit(0 if success else 1)

    else:
        print(f"Error: Invalid input: {input_path}")
        print("Must be a .mmd file or directory containing .mmd files")
        sys.exit(1)


if __name__ == "__main__":
    main()
