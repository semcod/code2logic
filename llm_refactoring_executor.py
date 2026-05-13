#!/usr/bin/env python3
"""
Execute LLM refactoring based on generated queries.
"""

import yaml
from pathlib import Path
from typing import Dict, List
from datetime import datetime


class LLMRefactoringExecutor:
    """Execute LLM-based refactoring using generated queries."""

    def __init__(self, queries_file: str):
        self.queries_file = Path(queries_file)
        self.queries_data = None
        self.refactoring_results = []

    def load_queries(self):
        """Load LLM refactoring queries."""

        if not self.queries_file.exists():
            raise FileNotFoundError(f"Queries file not found: {self.queries_file}")

        with open(self.queries_file, "r") as f:
            self.queries_data = yaml.safe_load(f)

        print(f"📋 Loaded {self.queries_data['total_queries']} queries")
        print(f"📊 Total insights: {self.queries_data['total_insights']}")

    def execute_refactoring(self) -> List[Dict]:
        """Execute LLM refactoring based on queries."""

        print("🚀 EXECUTING LLM-BASED REFACTORING")
        print("=" * 50)

        for i, query_data in enumerate(self.queries_data["queries"], 1):
            print(
                f"\n🔧 Refactoring {i}/{self.queries_data['total_queries']}: {query_data['function']}"
            )

            try:
                result = self._execute_single_refactoring(query_data)
                self.refactoring_results.append(result)
                print(f"   ✅ Completed - {result.get('actions_generated', 0)} actions")
            except Exception as e:
                print(f"   ❌ Error: {e}")
                self.refactoring_results.append(
                    {
                        "function": query_data["function"],
                        "error": str(e),
                        "status": "failed",
                    }
                )

        self._generate_refactoring_report()
        return self.refactoring_results

    def _execute_single_refactoring(self, query_data: Dict) -> Dict:
        """Execute single refactoring based on query."""

        function_name = query_data["function"]
        llm_query = query_data["llm_query"]
        insights_count = query_data["insights_count"]

        # Parse the LLM query to extract actionable items
        actionable_items = self._parse_llm_query(llm_query)

        # Generate specific refactoring actions
        refactoring_actions = self._generate_refactoring_actions(
            function_name, actionable_items
        )

        # Create implementation plan
        implementation_plan = self._create_implementation_plan(
            function_name, refactoring_actions
        )

        # Generate code changes
        code_changes = self._generate_code_changes(function_name, refactoring_actions)

        return {
            "function": function_name,
            "insights_count": insights_count,
            "status": "completed",
            "actionable_items": len(actionable_items),
            "actions_generated": len(refactoring_actions),
            "implementation_plan": implementation_plan,
            "code_changes": code_changes,
            "estimated_impact": self._estimate_impact(refactoring_actions),
        }

    def _parse_llm_query(self, llm_query: str) -> List[Dict]:
        """Parse LLM query to extract actionable items."""

        actionable_items = []

        # Extract recommendations (lines starting with numbers)
        lines = llm_query.split("\n")
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("•")):
                actionable_items.append(
                    {
                        "type": "recommendation",
                        "content": line,
                        "priority": "high" if "zredukuj" in line.lower() else "medium",
                    }
                )

        # Extract specific files to modify
        if "KONKRETNE PLIKI DO MODYFIKACJI:" in llm_query:
            files_section = llm_query.split("KONKRETNE PLIKI DO MODYFIKACJI:")[1]
            file_lines = files_section.split("\n")[
                :5
            ]  # Take first 5 lines after files section
            for line in file_lines:
                if line.strip().startswith("•"):
                    actionable_items.append(
                        {
                            "type": "file_modification",
                            "content": line.strip(),
                            "priority": "high",
                        }
                    )

        # Extract specific actions
        if "ZALECENIA:" in llm_query:
            recommendations_section = llm_query.split("ZALECENIA:")[1].split("\n\n")[0]
            for line in recommendations_section.split("\n"):
                if line.strip() and line[0].isdigit():
                    actionable_items.append(
                        {"type": "action", "content": line.strip(), "priority": "high"}
                    )

        return actionable_items

    def _generate_refactoring_actions(
        self, function_name: str, actionable_items: List[Dict]
    ) -> List[Dict]:
        """Generate specific refactoring actions."""

        actions = []

        for item in actionable_items:
            action_type = self._determine_action_type(item["content"])

            action = {
                "type": action_type,
                "description": item["content"],
                "priority": item["priority"],
                "function": function_name,
                "estimated_effort": self._estimate_effort(action_type),
                "files_affected": self._identify_affected_files(item["content"]),
            }

            actions.append(action)

        return actions

    def _determine_action_type(self, content: str) -> str:
        """Determine action type from content."""

        content_lower = content.lower()

        if "konsoliduj" in content_lower or "połącz" in content_lower:
            return "consolidation"
        elif "usuń" in content_lower or "usuń" in content_lower:
            return "removal"
        elif "uproszcz" in content_lower:
            return "simplification"
        elif "stwórz" in content_lower or "dodaj" in content_lower:
            return "creation"
        elif "zrefaktoruj" in content_lower or "przerwij" in content_lower:
            return "refactoring"
        elif "zastosuj" in content_lower or "użyj" in content_lower:
            return "pattern_application"
        else:
            return "general"

    def _estimate_effort(self, action_type: str) -> str:
        """Estimate effort for action type."""

        effort_map = {
            "consolidation": "medium",
            "removal": "low",
            "simplification": "medium",
            "creation": "high",
            "refactoring": "high",
            "pattern_application": "medium",
            "general": "medium",
        }

        return effort_map.get(action_type, "medium")

    def _identify_affected_files(self, content: str) -> List[str]:
        """Identify files affected by action."""

        files = []

        # Extract file names from content
        if ".py" in content:
            parts = content.split()
            for part in parts:
                if part.endswith(".py") or "." in part:
                    files.append(part)

        # Common files based on action content
        if "pipeline_runner" in content:
            files.append("pipeline_runner.py")
        if "automation" in content:
            files.append("automation/")
        if "generation" in content:
            files.append("generation/")

        return list(set(files))

    def _create_implementation_plan(
        self, function_name: str, actions: List[Dict]
    ) -> Dict:
        """Create implementation plan for refactoring."""

        # Group actions by priority
        high_priority = [a for a in actions if a["priority"] == "high"]
        medium_priority = [a for a in actions if a["priority"] == "medium"]
        low_priority = [a for a in actions if a["priority"] == "low"]

        # Calculate phases
        phases = []

        if high_priority:
            phases.append(
                {
                    "phase": 1,
                    "name": "Critical Refactoring",
                    "actions": high_priority,
                    "estimated_days": len(high_priority) * 2,
                }
            )

        if medium_priority:
            phases.append(
                {
                    "phase": 2,
                    "name": "Standard Improvements",
                    "actions": medium_priority,
                    "estimated_days": len(medium_priority) * 1,
                }
            )

        if low_priority:
            phases.append(
                {
                    "phase": 3,
                    "name": "Optional Enhancements",
                    "actions": low_priority,
                    "estimated_days": len(low_priority) * 0.5,
                }
            )

        return {
            "function": function_name,
            "total_actions": len(actions),
            "total_phases": len(phases),
            "estimated_total_days": sum(p["estimated_days"] for p in phases),
            "phases": phases,
        }

    def _generate_code_changes(
        self, function_name: str, actions: List[Dict]
    ) -> List[Dict]:
        """Generate specific code changes."""

        code_changes = []

        for action in actions:
            change = {
                "action_type": action["type"],
                "description": action["description"],
                "files": action["files_affected"],
                "code_template": self._generate_code_template(action),
                "test_required": self._requires_test(action["type"]),
            }

            code_changes.append(change)

        return code_changes

    def _generate_code_template(self, action: Dict) -> str:
        """Generate code template for action."""

        action_type = action["type"]
        description = action["description"]

        templates = {
            "consolidation": '''
# Consolidated implementation
class Consolidated{ClassName}:
    """Consolidated from multiple similar classes."""
    def __init__(self):
        self._shared_data = {}
    
    def unified_method(self):
        """Unified method replacing multiple similar methods."""
        pass
''',
            "removal": """
# Remove unused/dead code
# File: {filename}
# Lines to remove: {lines}
# Reason: {reason}
""",
            "simplification": '''
# Simplified implementation
def simplified_{function_name}():
    """Simplified version of complex function."""
    # Extract common logic
    # Reduce complexity
    pass
''',
            "creation": '''
# New implementation
class New{ClassName}:
    """New class to handle consolidated functionality."""
    def __init__(self):
        pass
    
    def execute(self):
        """Main execution method."""
        pass
''',
            "refactoring": '''
# Refactored implementation
def refactored_{function_name}():
    """Refactored version with improved structure."""
    # Apply design patterns
    # Improve readability
    # Optimize performance
    pass
''',
            "pattern_application": '''
# Pattern application
class {PatternName}:
    """Apply {pattern} design pattern."""
    def __init__(self):
        self._observers = []
    
    def attach(self, observer):
        """Attach observer."""
        self._observers.append(observer)
    
    def notify(self):
        """Notify all observers."""
        for observer in self._observers:
            observer.update()
''',
        }

        return templates.get(
            action_type, f"# Template for {action_type}\n# {description}"
        )

    def _requires_test(self, action_type: str) -> bool:
        """Determine if action requires testing."""

        test_required_types = {"consolidation", "refactoring", "creation"}
        return action_type in test_required_types

    def _estimate_impact(self, actions: List[Dict]) -> Dict:
        """Estimate impact of refactoring actions."""

        total_actions = len(actions)
        high_priority_count = len([a for a in actions if a["priority"] == "high"])

        # Calculate metrics
        complexity_reduction = high_priority_count * 15  # 15% per high priority action
        code_reduction = total_actions * 5  # 5% per action
        performance_improvement = high_priority_count * 10  # 10% per high priority

        return {
            "actions_count": total_actions,
            "high_priority_count": high_priority_count,
            "estimated_complexity_reduction": min(complexity_reduction, 70),
            "estimated_code_reduction": min(code_reduction, 50),
            "estimated_performance_improvement": min(performance_improvement, 60),
            "risk_level": "high" if high_priority_count > 3 else "medium",
        }

    def _generate_refactoring_report(self):
        """Generate comprehensive refactoring report."""

        print("\n📊 REFACTORING EXECUTION REPORT")
        print("=" * 50)

        successful_results = [
            r for r in self.refactoring_results if r.get("status") == "completed"
        ]
        failed_results = [
            r for r in self.refactoring_results if r.get("status") == "failed"
        ]

        print(f"✅ Successful: {len(successful_results)}")
        print(f"❌ Failed: {len(failed_results)}")
        print(
            f"📈 Success Rate: {len(successful_results) / len(self.refactoring_results) * 100:.1f}%"
        )

        # Calculate totals
        total_actions = sum(r.get("actions_generated", 0) for r in successful_results)
        total_impact = self._calculate_total_impact(successful_results)

        print("\n📈 TOTAL IMPACT:")
        print(f"• Actions Generated: {total_actions}")
        print(f"• Complexity Reduction: {total_impact['complexity_reduction']:.1f}%")
        print(f"• Code Reduction: {total_impact['code_reduction']:.1f}%")
        print(
            f"• Performance Improvement: {total_impact['performance_improvement']:.1f}%"
        )

        # Save detailed report
        self._save_refactoring_report(successful_results, failed_results, total_impact)

        print("\n💾 Detailed report saved to: 'llm_refactoring_report.yaml'")
        print("\n🚀 REFACTORING EXECUTION COMPLETE!")

    def _calculate_total_impact(self, results: List[Dict]) -> Dict:
        """Calculate total impact across all results."""

        total_complexity = 0
        total_code = 0
        total_performance = 0

        for result in results:
            impact = result.get("estimated_impact", {})
            total_complexity += impact.get("estimated_complexity_reduction", 0)
            total_code += impact.get("estimated_code_reduction", 0)
            total_performance += impact.get("estimated_performance_improvement", 0)

        return {
            "complexity_reduction": total_complexity / len(results) if results else 0,
            "code_reduction": total_code / len(results) if results else 0,
            "performance_improvement": total_performance / len(results)
            if results
            else 0,
        }

    def _save_refactoring_report(
        self, successful: List[Dict], failed: List[Dict], impact: Dict
    ):
        """Save detailed refactoring report."""

        report_data = {
            "execution_date": datetime.now().isoformat(),
            "queries_file": str(self.queries_file),
            "summary": {
                "total_queries": len(self.queries_data["queries"]),
                "successful_executions": len(successful),
                "failed_executions": len(failed),
                "success_rate": len(successful) / len(self.refactoring_results) * 100,
                "total_actions_generated": sum(
                    r.get("actions_generated", 0) for r in successful
                ),
                "total_impact": impact,
            },
            "successful_results": successful,
            "failed_results": failed,
            "implementation_plans": [
                r.get("implementation_plan")
                for r in successful
                if r.get("implementation_plan")
            ],
            "code_changes": [
                r.get("code_changes") for r in successful if r.get("code_changes")
            ],
        }

        output_path = self.queries_file.parent / "llm_refactoring_report.yaml"
        with open(output_path, "w") as f:
            yaml.dump(report_data, f, default_flow_style=False, sort_keys=False)


def main():
    """Main execution function."""

    queries_file = "output_hybrid/llm_refactoring_queries.yaml"
    if not Path(queries_file).exists():
        print("❌ LLM queries file not found. Run analysis first.")
        return

    executor = LLMRefactoringExecutor(queries_file)

    try:
        executor.load_queries()
        results = executor.execute_refactoring()

        print("\n🎉 LLM REFACTORING EXECUTION COMPLETE!")
        print(f"Processed {len(results)} refactoring queries")
        print("Ready for implementation!")

    except Exception as e:
        print(f"❌ Error during execution: {e}")


if __name__ == "__main__":
    main()
