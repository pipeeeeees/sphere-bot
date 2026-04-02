"""
Command Registry System
Manages bot commands in a scalable, table-driven manner.
"""

from typing import Callable, Dict, List, Any, Optional
import inspect


class CommandRegistry:
    """
    Registry for managing Discord bot commands.
    
    Commands are stored as dictionaries with:
    - name: command name (string)
    - callback: async function to execute
    - description: short description of what the command does
    """
    
    def __init__(self):
        self.commands: List[Dict[str, Any]] = []
    
    def register(self, name: str, callback: Callable, description: str) -> None:
        """
        Register a new command.
        
        Args:
            name: Command name (used as !command in Discord)
            callback: Async function that executes the command (receives ctx)
            description: Short description of the command
        """
        if not inspect.iscoroutinefunction(callback):
            raise ValueError(f"Callback for command '{name}' must be async")
        
        # Check if command already exists
        if self.get_command(name):
            raise ValueError(f"Command '{name}' already registered")
        
        self.commands.append({
            "name": name,
            "callback": callback,
            "description": description
        })
    
    def get_command(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a command by name.
        
        Args:
            name: Command name
            
        Returns:
            Command dictionary or None if not found
        """
        for cmd in self.commands:
            if cmd["name"] == name:
                return cmd
        return None
    
    def get_all_commands(self) -> List[Dict[str, Any]]:
        """
        Get all registered commands.
        
        Returns:
            List of command dictionaries
        """
        return self.commands.copy()
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a command.
        
        Args:
            name: Command name
            
        Returns:
            True if command was removed, False if not found
        """
        for i, cmd in enumerate(self.commands):
            if cmd["name"] == name:
                self.commands.pop(i)
                return True
        return False
