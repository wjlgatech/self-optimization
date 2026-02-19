#!/usr/bin/env python3
import sys
import os
import json
from datetime import datetime
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.activity_scanner import ActivityScanner
from src.reflection_generator import ReflectionGenerator
from src.config_loader import ConfigLoader

class SystemOrchestrator:
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.state_dir = Path(workspace_root) / 'self-optimization' / 'state'
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self.scanner = ActivityScanner(workspace_root)
        self.config_loader = ConfigLoader(workspace_root)
        self.reflection_gen = ReflectionGenerator(self.scanner)

    def status_check(self) -> dict:
        """Get system status"""
        try:
            idle_duration = self.scanner.get_idle_duration()
            activity = self.scanner.calculate_activity_score(time_window_hours=24)
            
            status = {
                'agent_id': 'loopy-0',
                'timestamp': datetime.now().isoformat(),
                'llm_available': True,
                'workspace_root': self.workspace_root,
                'repositories_found': len(self.scanner.subdirectories),
                'current_idle_hours': idle_duration,
                'activities_24h': activity['total_commits'],
                'repos_active_24h': activity['repositories_active'],
                'system_status': 'operational'
            }
            
            print(json.dumps(status, indent=2))
            self._save_state('status', status)
            return status
        except Exception as e:
            print(f"ERROR in status_check: {e}", file=sys.stderr)
            return {'error': str(e)}

    def idle_check(self) -> dict:
        """Check idle state and trigger interventions if needed"""
        try:
            idle_duration = self.scanner.get_idle_duration()
            activity = self.scanner.calculate_activity_score(time_window_hours=2)
            
            triggered = idle_duration > 2.0  # 2-hour threshold
            
            result = {
                'timestamp': datetime.now().isoformat(),
                'idle_duration_hours': idle_duration,
                'activities_found': activity['total_commits'],
                'idle_rate': activity['is_idle'],
                'triggered': triggered,
                'repositories_checked': len(self.scanner.subdirectories),
                'breakdown': activity['breakdown_by_repo']
            }
            
            print(json.dumps(result, indent=2))
            self._save_state('idle_check', result)
            
            if triggered:
                print("\n⚠️  IDLE STATE DETECTED - Triggering interventions")
            
            return result
        except Exception as e:
            print(f"ERROR in idle_check: {e}", file=sys.stderr)
            return {'error': str(e)}

    def daily_review(self) -> dict:
        """Generate daily reflection based on actual activity"""
        try:
            reflection = self.reflection_gen.generate_daily_reflection()
            
            # Create reflection file
            today = datetime.now().strftime('%Y-%m-%d')
            reflection_dir = Path(self.workspace_root) / 'memory' / 'daily-reflections'
            reflection_dir.mkdir(parents=True, exist_ok=True)
            reflection_path = reflection_dir / f'{today}-reflection.md'
            
            self.reflection_gen.save_reflection(reflection, str(reflection_path))
            
            result = {
                'timestamp': datetime.now().isoformat(),
                'activities_found': reflection['activity_summary']['total_commits'],
                'repositories_active': reflection['activity_summary']['repositories_active'],
                'is_idle': reflection['activity_summary']['is_idle'],
                'productivity_score': reflection['quality_metrics']['productivity_score'],
                'achievements': len(reflection['achievements']),
                'reflection_saved_to': str(reflection_path)
            }
            
            print(json.dumps(result, indent=2))
            print(f"\nReflection saved to: {reflection_path}")
            
            self._save_state('daily_review', result)
            return result
        except Exception as e:
            print(f"ERROR in daily_review: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return {'error': str(e)}

    def _save_state(self, check_type: str, result: dict):
        """Persist state to JSON"""
        try:
            # Save specific check result
            state_file = self.state_dir / f'{check_type}.json'
            with open(state_file, 'w') as f:
                json.dump(result, f, indent=2)
            
            # Also update last_run.json
            last_run_file = self.state_dir / 'last_run.json'
            last_run = {}
            if last_run_file.exists():
                with open(last_run_file, 'r') as f:
                    last_run = json.load(f)
            
            last_run[check_type] = result
            with open(last_run_file, 'w') as f:
                json.dump(last_run, f, indent=2)
        except Exception as e:
            print(f"ERROR saving state: {e}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description='Loopy-0 Self-Optimization System')
    parser.add_argument('command', choices=['status', 'idle-check', 'daily-review'],
                       help='Command to execute')
    
    args = parser.parse_args()
    
    workspace_root = os.path.expanduser('~/.openclaw/workspace')
    orchestrator = SystemOrchestrator(workspace_root)
    
    if args.command == 'status':
        orchestrator.status_check()
    elif args.command == 'idle-check':
        orchestrator.idle_check()
    elif args.command == 'daily-review':
        orchestrator.daily_review()

if __name__ == '__main__':
    main()
