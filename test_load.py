#!/usr/bin/env python
"""Test that bot loads configuration correctly without connecting."""

from toast import command_registry, schedule_registry

print('✓ Bot module loaded')
print(f'✓ Commands registered: {len(command_registry.get_all_commands())}')
print(f'✓ Schedules registered: {len(schedule_registry.get_all_schedules())}')
print('\nLoaded commands:')
for cmd in command_registry.get_all_commands():
    print(f'  - !{cmd["name"]}: {cmd["description"]}')
print('\nLoaded schedules:')
for schedule in schedule_registry.get_all_schedules():
    print(f'  - {schedule["name"]}: {schedule["message"][:50]}...')
