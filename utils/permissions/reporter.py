import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import csv
from pathlib import Path
import json
from dataclasses import dataclass
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from auth.models import Player, Permission, Role, PlayerRole
from auth.service import AuthService, ScopeType
from teams.models import Team
from competitions.models.tournaments import Tournament
from roles.models import PermissionAuditResult

class PermissionReporter:
    """Utility for generating permission audit reports"""
    
    @staticmethod
    def generate_csv_report(results: List[PermissionAuditResult], output_path: Path):
        """Generate CSV report of permission audit results"""
        with output_path.open('w', newline='') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow([
                'Player ID', 'Name', 'Steam ID', 'Roles',
                'Global Permissions', 'Team Permissions',
                'Tournament Permissions', 'Issues'
            ])
            
            # Write data
            for result in results:
                writer.writerow([
                    result.player_uid,
                    result.player_name,
                    result.steam_id,
                    ','.join(result.roles),
                    ','.join(result.global_permissions),
                    json.dumps(result.team_permissions),
                    json.dumps(result.tournament_permissions),
                    ';'.join(result.issues)
                ])

    @staticmethod
    def generate_json_report(results: List[PermissionAuditResult], output_path: Path):
        """Generate JSON report of permission audit results"""
        report_data = []
        for result in results:
            report_data.append({
                'player_id': result.player_uid,
                'name': result.player_name,
                'steam_id': result.steam_id,
                'roles': list(result.roles),
                'global_permissions': list(result.global_permissions),
                'team_permissions': {
                    k: list(v) for k, v in result.team_permissions.items()
                },
                'tournament_permissions': {
                    k: list(v) for k, v in result.tournament_permissions.items()
                },
                'issues': result.issues
            })
            
        with output_path.open('w') as f:
            json.dump(report_data, f, indent=2)

    @staticmethod
    def generate_summary_report(results: List[PermissionAuditResult]) -> str:
        """Generate a text summary of permission audit results"""
        total_players = len(results)
        players_with_issues = len([r for r in results if r.issues])
        total_issues = sum(len(r.issues) for r in results)
        
        # Count permission distribution
        global_perms = set()
        team_perms = set()
        tournament_perms = set()
        for result in results:
            global_perms.update(result.global_permissions)
            for perms in result.team_permissions.values():
                team_perms.update(perms)
            for perms in result.tournament_permissions.values():
                tournament_perms.update(perms)
                
        summary = [
            f"Permission Audit Summary",
            f"----------------------",
            f"Total players audited: {total_players}",
            f"Players with issues: {players_with_issues}",
            f"Total issues found: {total_issues}",
            f"",
            f"Permission Distribution:",
            f"  Global permissions: {len(global_perms)}",
            f"  Team permissions: {len(team_perms)}",
            f"  Tournament permissions: {len(tournament_perms)}",
            f"",
            f"Top Issues:"
        ]
        
        # Count issue frequency
        issue_counts: Dict[str, int] = {}
        for result in results:
            for issue in result.issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
                
        # Add top 5 most common issues
        for issue, count in sorted(
            issue_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]:
            summary.append(f"  - {issue}: {count} occurrences")
            
        return '\n'.join(summary)