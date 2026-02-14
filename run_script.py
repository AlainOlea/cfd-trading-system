#!/usr/bin/env python3
"""
Trading System Script Manager
==============================
Centralized script runner with category-based organization
Usage: python3 run_script.py <category> <script_name> [options]
"""

import sys
import os
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML not installed. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml


class ScriptManager:
    def __init__(self, config_file="scripts.yaml"):
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self):
        """Load scripts configuration from YAML"""
        try:
            with open(self.config_file) as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"❌ Configuration file not found: {self.config_file}")
            sys.exit(1)

    def list_categories(self):
        """List all available categories"""
        print("\n" + "="*80)
        print("📚 Available Script Categories")
        print("="*80 + "\n")

        for category, scripts in self.config["scripts"].items():
            if isinstance(scripts, dict) and "description" in scripts:
                desc = scripts.get("description", "")
                count = len([k for k in scripts.keys() if k != "description"])
                print(f"📁 {category:15} : {desc:40} ({count} scripts)")

        print("\n" + "="*80)

    def list_scripts_in_category(self, category):
        """List all scripts in a category"""
        if category not in self.config["scripts"]:
            print(f"❌ Category '{category}' not found")
            self.list_categories()
            return

        scripts = self.config["scripts"][category]
        desc = scripts.get("description", "")

        print("\n" + "="*80)
        print(f"📁 {category.upper()} - {desc}")
        print("="*80 + "\n")

        for script_name, script_info in scripts.items():
            if script_name == "description":
                continue

            if isinstance(script_info, dict):
                script_desc = script_info.get("description", "")
                print(f"  🔹 {script_name:25} : {script_desc}")

        print("\n" + "="*80)
        print(f"Usage: python3 run_script.py {category} <script_name>\n")

    def run_script(self, category, script_name, extra_args=None):
        """Execute a script from a category"""
        if category not in self.config["scripts"]:
            print(f"❌ Category '{category}' not found\n")
            self.list_categories()
            return False

        scripts = self.config["scripts"][category]

        if script_name not in scripts:
            print(f"❌ Script '{script_name}' not found in category '{category}'\n")
            self.list_scripts_in_category(category)
            return False

        script_info = scripts[script_name]

        if isinstance(script_info, dict) and "command" in script_info:
            command = script_info["command"]
            description = script_info.get("description", "")

            print("\n" + "="*80)
            print(f"▶️  Running: {description}")
            print("="*80 + "\n")

            # Activate venv first
            if os.path.exists("venv/bin/activate"):
                command = f"source venv/bin/activate && {command}"

            # Add extra arguments if provided
            if extra_args:
                command = f"{command} {' '.join(extra_args)}"

            print(f"📋 Command: {command}\n")
            print("="*80 + "\n")

            try:
                # Run in bash shell to support source and pipes
                result = subprocess.run(
                    command,
                    shell=True,
                    executable="/bin/bash"
                )
                return result.returncode == 0
            except KeyboardInterrupt:
                print("\n⏹️  Interrupted by user")
                return False
            except Exception as e:
                print(f"❌ Error: {e}")
                return False
        else:
            print(f"❌ Invalid script configuration")
            return False

    def show_help(self):
        """Show help text"""
        help_text = self.config.get("help_text", "")
        print(help_text)

    def show_workflows(self):
        """Show available workflows"""
        workflows = self.config["scripts"].get("workflows", {})

        print("\n" + "="*80)
        print("⚙️  Available Workflows (Multi-step Commands)")
        print("="*80 + "\n")

        for workflow_name, workflow_info in workflows.items():
            if workflow_name == "description":
                continue

            if isinstance(workflow_info, dict):
                desc = workflow_info.get("description", "")
                print(f"  🔄 {workflow_name:25} : {desc}")

        print("\n" + "="*80)
        print("Usage: python3 run_script.py workflows <workflow_name>\n")


def main():
    """Main entry point"""
    manager = ScriptManager()

    # No arguments
    if len(sys.argv) < 2:
        manager.show_help()
        return

    command = sys.argv[1].lower()

    # Help command
    if command in ["help", "-h", "--help"]:
        manager.show_help()
        return

    # List all categories
    if command == "list":
        if len(sys.argv) > 2:
            manager.list_scripts_in_category(sys.argv[2])
        else:
            manager.list_categories()
        return

    # Run a script
    if len(sys.argv) >= 3:
        category = sys.argv[1]
        script_name = sys.argv[2]
        extra_args = sys.argv[3:] if len(sys.argv) > 3 else None

        success = manager.run_script(category, script_name, extra_args)
        sys.exit(0 if success else 1)
    else:
        print(f"❌ Missing script name")
        print(f"Usage: python3 run_script.py <category> <script_name>")
        manager.show_help()


if __name__ == "__main__":
    main()
