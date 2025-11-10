"""
BOT PROCESS MANAGER
===================
Manage bot process lifecycle (start, stop, status)
"""

import os
import signal
import subprocess
import psutil
from pathlib import Path
from typing import Optional, Dict
from loguru import logger

class BotManager:
    """
    Manage the trading bot process
    """

    def __init__(self, pid_file: str = "/tmp/cryptonita_bot.pid"):
        """
        Initialize bot manager

        Args:
            pid_file: Path to store bot process ID
        """
        self.pid_file = Path(pid_file)
        self.bot_script = Path(__file__).parent.parent.parent / "run_bot.py"

    def is_running(self) -> bool:
        """
        Check if bot is currently running

        Returns:
            True if bot process is running
        """
        if not self.pid_file.exists():
            return False

        try:
            pid = int(self.pid_file.read_text().strip())
            return psutil.pid_exists(pid)
        except (ValueError, FileNotFoundError):
            return False

    def get_pid(self) -> Optional[int]:
        """
        Get bot process ID

        Returns:
            Process ID or None if not running
        """
        if not self.pid_file.exists():
            return None

        try:
            pid = int(self.pid_file.read_text().strip())
            if psutil.pid_exists(pid):
                return pid
            return None
        except (ValueError, FileNotFoundError):
            return None

    def get_status(self) -> Dict:
        """
        Get detailed bot status

        Returns:
            Dict with status information
        """
        pid = self.get_pid()

        if pid is None:
            return {
                "running": False,
                "pid": None,
                "cpu_percent": 0,
                "memory_mb": 0,
                "uptime_seconds": 0
            }

        try:
            process = psutil.Process(pid)
            return {
                "running": True,
                "pid": pid,
                "cpu_percent": process.cpu_percent(interval=0.1),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "uptime_seconds": (psutil.time.time() - process.create_time())
            }
        except psutil.NoSuchProcess:
            return {
                "running": False,
                "pid": None,
                "cpu_percent": 0,
                "memory_mb": 0,
                "uptime_seconds": 0
            }

    def start(self, mode: str = "auto") -> Dict:
        """
        Start the trading bot

        Args:
            mode: Trading mode ('auto' or 'manual')

        Returns:
            Dict with success status and message
        """
        # Check if already running
        if self.is_running():
            return {
                "success": False,
                "message": "Bot is already running",
                "pid": self.get_pid()
            }

        try:
            # Start bot process in background
            process = subprocess.Popen(
                ["python3", str(self.bot_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Detach from parent
                cwd=str(self.bot_script.parent.parent)
            )

            # Save PID
            self.pid_file.write_text(str(process.pid))

            logger.success(f"✅ Bot started with PID {process.pid}")

            return {
                "success": True,
                "message": f"Bot started successfully in {mode} mode",
                "pid": process.pid
            }

        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}")
            return {
                "success": False,
                "message": f"Failed to start bot: {str(e)}",
                "pid": None
            }

    def stop(self, reason: str = "Manual stop") -> Dict:
        """
        Stop the trading bot

        Args:
            reason: Reason for stopping

        Returns:
            Dict with success status and message
        """
        pid = self.get_pid()

        if pid is None:
            return {
                "success": False,
                "message": "Bot is not running"
            }

        try:
            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit (max 10 seconds)
            try:
                process = psutil.Process(pid)
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                # Force kill if doesn't exit gracefully
                os.kill(pid, signal.SIGKILL)
                logger.warning(f"⚠️ Bot process {pid} force killed")

            # Remove PID file
            if self.pid_file.exists():
                self.pid_file.unlink()

            logger.success(f"✅ Bot stopped: {reason}")

            return {
                "success": True,
                "message": f"Bot stopped successfully: {reason}"
            }

        except ProcessLookupError:
            # Process already dead
            if self.pid_file.exists():
                self.pid_file.unlink()

            return {
                "success": True,
                "message": "Bot process was already stopped"
            }

        except Exception as e:
            logger.error(f"❌ Failed to stop bot: {e}")
            return {
                "success": False,
                "message": f"Failed to stop bot: {str(e)}"
            }

    def restart(self, mode: str = "auto") -> Dict:
        """
        Restart the trading bot

        Args:
            mode: Trading mode

        Returns:
            Dict with success status and message
        """
        # Stop first
        stop_result = self.stop(reason="Restart requested")

        if not stop_result["success"] and self.is_running():
            return {
                "success": False,
                "message": "Failed to stop bot for restart"
            }

        # Wait a bit
        import time
        time.sleep(2)

        # Start again
        return self.start(mode=mode)
