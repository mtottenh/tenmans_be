#!/usr/bin/env python3

import asyncio
import click
from datetime import datetime
import sys
import os
from typing import Optional

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from audit.schemas import AuditEventType 
from services.audit import audit_service
from db.main import get_session

def parse_date(ctx, param, date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string in YYYY-MM-DD format"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise click.BadParameter('Date must be in YYYY-MM-DD format')

def format_event(event, include_details: bool = False):
    """Format a single audit event for display"""
    output = [
        f"\nEvent ID: {event.id}",
        f"Timestamp: {event.timestamp}",
        f"Action: {event.action_type}",
        f"Entity: {event.entity_type} (ID: {event.entity_id})",
        f"Actor ID: {event.actor_id}"
    ]
    
    if event.action_type == AuditEventType.STATUS_CHANGE:
        output.extend([
            f"Status Change: {event.previous_status} -> {event.new_status}",
            f"Reason: {event.transition_reason}"
        ])
        
    if include_details and event.details:
        output.append("\nDetails:")
        if isinstance(event.details, str):
            output.append(f" {event.details}")
        else:
            for key, value in event.details.items():
                output.append(f"  {key}: {value}")
            
    return "\n".join(output)

@click.group()
def cli():
    """Audit Log Query Utility"""
    pass

@cli.command()
@click.option('--action-type', type=click.Choice([t.value for t in AuditEventType]),
              help='Filter by action type')
@click.option('--entity-type', default=None, help='Filter by entity type (e.g., Player, Team)')
@click.option('--entity-id', default=None, help='Filter by specific entity ID')
@click.option('--actor-id',  default=None, help='Filter by actor ID')
@click.option('--start-date', default=None, help='Start date (YYYY-MM-DD)', callback=parse_date)
@click.option('--end-date', default=None, help='End date (YYYY-MM-DD)', callback=parse_date)
@click.option('--limit', default=100, help='Limit number of results')
@click.option('--offset', default=0, help='Number of results to skip')
@click.option('--include-details', is_flag=True, help='Include full event details')
@click.option('--stats', is_flag=True, help='Include query statistics')
async def list(action_type, entity_type, entity_id, actor_id, start_date, end_date,
              limit, offset, include_details, stats):
    """List audit events with optional filtering"""
    async for session in get_session():
        result = await audit_service.query_events(
            session=session,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            start_date=start_date,
            end_date=end_date,
            include_details=include_details,
            offset=offset,
            limit=limit,
            calculate_stats=stats
        )
        
        # Print results header
        click.echo(f"\nFound {result.total_count} events" + 
                  f" (showing {len(result.events)})")
        
        # Print events
        for event in result.events:
            click.echo(format_event(event, include_details))
            click.echo("-" * 80)
            
        # Print statistics if requested
        if stats and result.statistics:
            click.echo("\nQuery Statistics:")
            for key, value in result.statistics.items():
                click.echo(f"{key}: {value}")

@cli.command()
@click.option('--days', default=7, help='Number of days to include in summary')
@click.option('--entity-type', help='Filter by entity type')
async def summary(days, entity_type):
    """Get summary statistics of audit events"""
    async for session in get_session():
        stats = await audit_service.get_summary_statistics(
            session=session,
            days=days,
            entity_type=entity_type
        )
        
        click.echo(f"\nAudit Event Summary (Last {stats['period_days']} days)")
        click.echo(f"Total Events: {stats['total_events']}")
        
        click.echo("\nEvents by Action Type:")
        for action_type, count in stats['action_counts'].items():
            click.echo(f"  {action_type}: {count}")
            
        click.echo("\nEvents by Entity Type:")
        for entity_type, count in stats['entity_counts'].items():
            click.echo(f"  {entity_type}: {count}")
            
        click.echo("\nTop 10 Actors:")
        for actor_id, count in stats['top_actors'].items():
            click.echo(f"  Actor {actor_id}: {count} events")

@cli.command()
@click.argument('entity_type')
@click.argument('entity_id')
@click.option('--include-cascaded/--no-cascaded', default=True,
              help='Include cascaded events')
async def history(entity_type, entity_id, include_cascaded):
    """Get complete history for an entity"""
    async for session in get_session():
        events = await audit_service.get_entity_history(
            session=session,
            entity_type=entity_type,
            entity_id=entity_id,
            include_cascaded=include_cascaded
        )
        
        if not events:
            click.echo(f"No history found for {entity_type} with ID {entity_id}")
            return
            
        click.echo(f"\nHistory for {entity_type} (ID: {entity_id})")
        click.echo(f"Found {len(events)} events\n")
        
        for event in events:
            click.echo(format_event(event, include_details=True))
            click.echo("-" * 80)

def run_async_command(coro):
    """Helper function to run async commands"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)

def main():
    """Entry point for the CLI"""
    # Wrap Click commands to handle async
    original_list = list.callback
    original_summary = summary.callback
    original_history = history.callback
    
    list.callback = lambda *args, **kwargs: run_async_command(
        original_list(*args, **kwargs)
    )
    summary.callback = lambda *args, **kwargs: run_async_command(
        original_summary(*args, **kwargs)
    )
    history.callback = lambda *args, **kwargs: run_async_command(
        original_history(*args, **kwargs)
    )
    
    cli()

if __name__ == "__main__":
    main()