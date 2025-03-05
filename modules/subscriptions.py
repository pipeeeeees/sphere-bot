import json
import os

def manage_pollen_subscription(discord_id: int) -> str:
    """
    Adds or removes a Discord ID from pollen_sub.json in the config/ directory.
    If the file does not exist, it is created with default metadata.
    If metadata fields (time, days) change in the script, the JSON file updates accordingly.

    :param discord_id: Discord user ID to add or remove
    :return: "added" if added, "removed" if removed
    """
    config_path = "config/pollen_sub.json"
    
    # Ensure config directory exists
    os.makedirs("config", exist_ok=True)
    
    # Default metadata
    metadata = {
        "time": "22:54", 
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "subscribers": []
    }
    
    # Load existing subscriptions if the file exists
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if not isinstance(data, dict) or "subscribers" not in data:
                    data = metadata  # Reset if file is corrupted
            except json.JSONDecodeError:
                data = metadata  # Reset if file is corrupted
    else:
        data = metadata
    
    # Ensure metadata consistency (overwrite time/days if they differ)
    data["time"] = metadata["time"]
    data["days"] = metadata["days"]

    # Add or remove the Discord ID
    if discord_id in data["subscribers"]:
        data["subscribers"].remove(discord_id)
        action = "removed"
    else:
        data["subscribers"].append(discord_id)
        action = "added"
    
    # Save the updated data back to the file
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    
    return action

if __name__ == "__main__":
    # Example usage
    discord_id = 326676188057567232  # Replace with actual Discord ID
    action = manage_pollen_subscription(discord_id)
    print(f"Discord ID {discord_id} was {action}.")

    # Manage another ID
    discord_id = 431121754568523796
    action = manage_pollen_subscription(discord_id)
    print(f"Discord ID {discord_id} was {action}.")
