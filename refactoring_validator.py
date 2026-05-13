#!/usr/bin/env python3
"""
Final validation and testing of the complete refactoring pipeline.
"""

import yaml
from pathlib import Path
from typing import Dict, List
from datetime import datetime
import sys


class RefactoringValidator:
    """Validate and test the complete refactoring pipeline."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.validation_results = []
        self.test_results = []

    def run_complete_validation(self):
        """Run complete validation of the refactoring pipeline."""

        print("🧪 RUNNING COMPLETE REFACTORING VALIDATION")
        print("=" * 60)

        # Validate all generated files
        self._validate_generated_files()

        # Test refactored components
        self._test_refactored_components()

        # Validate implementation completeness
        self._validate_implementation_completeness()

        # Generate validation report
        self._generate_validation_report()

        print("\n🎉 VALIDATION COMPLETE!")

    def _validate_generated_files(self):
        """Validate all generated files."""

        print("\n📁 VALIDATING GENERATED FILES")
        print("-" * 40)

        files_to_validate = [
            "output_hybrid/index.html",
            "output_hybrid/graph_viewer.html",
            "output_hybrid/llm_refactoring_queries.yaml",
            "output_hybrid/llm_refactoring_report.yaml",
            "project_summary.yaml",
            "refactoring_implementation_report.yaml",
            "pipeline_runner_utils_improved.py",
            "complexity_reduction_examples.py",
            "general_refactoring_template.py",
        ]

        for file_path in files_to_validate:
            full_path = self.base_path / file_path
            if full_path.exists():
                validation_result = self._validate_single_file(full_path)
                self.validation_results.append(validation_result)

                status = "✅" if validation_result["valid"] else "❌"
                print(f"  {status} {file_path} - {validation_result['status']}")
            else:
                print(f"  ❌ {file_path} - MISSING")
                self.validation_results.append(
                    {"file": file_path, "valid": False, "status": "MISSING", "size": 0}
                )

    def _validate_single_file(self, file_path: Path) -> Dict:
        """Validate a single file."""

        try:
            stat = file_path.stat()
            size_kb = stat.st_size / 1024

            # Basic validation based on file type
            if file_path.suffix == ".html":
                valid = self._validate_html_file(file_path)
                status = "VALID HTML" if valid else "INVALID HTML"
            elif file_path.suffix == ".yaml":
                valid = self._validate_yaml_file(file_path)
                status = "VALID YAML" if valid else "INVALID YAML"
            elif file_path.suffix == ".py":
                valid = self._validate_python_file(file_path)
                status = "VALID PYTHON" if valid else "INVALID PYTHON"
            else:
                valid = True
                status = "VALID"

            return {
                "file": str(file_path),
                "valid": valid,
                "status": status,
                "size": size_kb,
            }

        except Exception as e:
            return {
                "file": str(file_path),
                "valid": False,
                "status": f"ERROR: {e}",
                "size": 0,
            }

    def _validate_html_file(self, file_path: Path) -> bool:
        """Validate HTML file."""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Basic HTML validation
            required_elements = [
                "<!DOCTYPE html>",
                "<html",
                "<head>",
                "<body>",
                "</html>",
            ]
            return all(element in content for element in required_elements)

        except Exception:
            return False

    def _validate_yaml_file(self, file_path: Path) -> bool:
        """Validate YAML file."""

        try:
            with open(file_path, "r") as f:
                yaml.safe_load(f)
            return True
        except Exception:
            return False

    def _validate_python_file(self, file_path: Path) -> bool:
        """Validate Python file."""

        try:
            # Try to compile the Python file
            with open(file_path, "r") as f:
                content = f.read()
            compile(content, str(file_path), "exec")
            return True
        except Exception:
            return False

    def _test_refactored_components(self):
        """Test refactored components."""

        print("\n🧪 TESTING REFACTORED COMPONENTS")
        print("-" * 40)

        # Test improved pipeline runner utils
        self._test_pipeline_runner_utils()

        # Test complexity reduction examples
        self._test_complexity_reduction_examples()

        # Test general refactoring template
        self._test_general_refactoring_template()

    def _test_pipeline_runner_utils(self):
        """Test improved pipeline runner utils."""

        print("  🔧 Testing pipeline_runner_utils_improved.py...")

        try:
            # Import and test the improved utils
            sys.path.insert(0, str(self.base_path))
            import pipeline_runner_utils_improved

            # Test ConsolidatedMarkdownWrapper
            wrapper = pipeline_runner_utils_improved.ConsolidatedMarkdownWrapper()
            wrapper.print("Test message")
            wrapper.enable_debug()
            wrapper.print("Debug message")
            output = wrapper.get_output()

            test_passed = len(output) >= 2 and "Test message" in str(output)

            self.test_results.append(
                {
                    "component": "pipeline_runner_utils_improved",
                    "test": "ConsolidatedMarkdownWrapper",
                    "passed": test_passed,
                    "details": f"Output buffer size: {len(output)}",
                }
            )

            status = "✅" if test_passed else "❌"
            print(
                f"    {status} ConsolidatedMarkdownWrapper - {'PASSED' if test_passed else 'FAILED'}"
            )

        except Exception as e:
            self.test_results.append(
                {
                    "component": "pipeline_runner_utils_improved",
                    "test": "Import",
                    "passed": False,
                    "details": str(e),
                }
            )
            print(f"    ❌ Import failed: {e}")

    def _test_complexity_reduction_examples(self):
        """Test complexity reduction examples."""

        print("  🔧 Testing complexity_reduction_examples.py...")

        try:
            # Import and test the complexity reduction examples
            import complexity_reduction_examples

            # Test ConsolidatedDataNode
            node = complexity_reduction_examples.ConsolidatedDataNode(
                "test_node", "test_type", {"value": 42}
            )
            node.add_connection("other_node")

            test_passed = node.id == "test_node" and len(node.connections) == 1

            self.test_results.append(
                {
                    "component": "complexity_reduction_examples",
                    "test": "ConsolidatedDataNode",
                    "passed": test_passed,
                    "details": f"Node connections: {len(node.connections)}",
                }
            )

            status = "✅" if test_passed else "❌"
            print(
                f"    {status} ConsolidatedDataNode - {'PASSED' if test_passed else 'FAILED'}"
            )

            # Test ConsolidatedProcessor
            processor = complexity_reduction_examples.ConsolidatedProcessor()
            result = processor.process({"type": "unknown", "data": "test"})

            test_passed2 = result.get("processed") == True

            self.test_results.append(
                {
                    "component": "complexity_reduction_examples",
                    "test": "ConsolidatedProcessor",
                    "passed": test_passed2,
                    "details": f"Process result: {result.get('processed', False)}",
                }
            )

            status = "✅" if test_passed2 else "❌"
            print(
                f"    {status} ConsolidatedProcessor - {'PASSED' if test_passed2 else 'FAILED'}"
            )

        except Exception as e:
            self.test_results.append(
                {
                    "component": "complexity_reduction_examples",
                    "test": "Import",
                    "passed": False,
                    "details": str(e),
                }
            )
            print(f"    ❌ Import failed: {e}")

    def _test_general_refactoring_template(self):
        """Test general refactoring template."""

        print("  🔧 Testing general_refactoring_template.py...")

        try:
            # Import and test the general refactoring template
            import general_refactoring_template

            # Test RefactoredComponent
            component = general_refactoring_template.RefactoredComponent()
            component.configure({"test_setting": True})
            result = component.execute({"input": "test"})

            test_passed = result.get("success") == True

            self.test_results.append(
                {
                    "component": "general_refactoring_template",
                    "test": "RefactoredComponent",
                    "passed": test_passed,
                    "details": f"Execution success: {result.get('success', False)}",
                }
            )

            status = "✅" if test_passed else "❌"
            print(
                f"    {status} RefactoredComponent - {'PASSED' if test_passed else 'FAILED'}"
            )

            # Test factory function
            component2 = general_refactoring_template.create_refactored_component(
                {"factory": True}
            )
            status2 = component2.get_status().get("configured", False)

            test_passed2 = status2 == True

            self.test_results.append(
                {
                    "component": "general_refactoring_template",
                    "test": "Factory Function",
                    "passed": test_passed2,
                    "details": f"Factory configured: {status2}",
                }
            )

            status = "✅" if test_passed2 else "❌"
            print(
                f"    {status} Factory Function - {'PASSED' if test_passed2 else 'FAILED'}"
            )

        except Exception as e:
            self.test_results.append(
                {
                    "component": "general_refactoring_template",
                    "test": "Import",
                    "passed": False,
                    "details": str(e),
                }
            )
            print(f"    ❌ Import failed: {e}")

    def _validate_implementation_completeness(self):
        """Validate implementation completeness."""

        print("\n📊 VALIDATING IMPLEMENTATION COMPLETENESS")
        print("-" * 40)

        # Check if all expected components are present
        expected_components = {
            "hybrid_export": "output_hybrid/index.yaml",
            "visualization_tree": "output_hybrid/index.html",
            "visualization_graph": "output_hybrid/graph_viewer.html",
            "analysis_queries": "output_hybrid/llm_refactoring_queries.yaml",
            "refactoring_report": "output_hybrid/llm_refactoring_report.yaml",
            "implementation_report": "refactoring_implementation_report.yaml",
            "project_summary": "project_summary.yaml",
        }

        completeness_score = 0
        total_components = len(expected_components)

        for component, file_path in expected_components.items():
            full_path = self.base_path / file_path
            if full_path.exists():
                completeness_score += 1
                print(f"  ✅ {component} - PRESENT")
            else:
                print(f"  ❌ {component} - MISSING")

        # Calculate completeness percentage
        completeness_percentage = (completeness_score / total_components) * 100

        print(f"\n📈 COMPLETENESS SCORE: {completeness_percentage:.1f}%")
        print(f"  • Components present: {completeness_score}/{total_components}")

        # Validate implementation quality
        self._validate_implementation_quality()

    def _validate_implementation_quality(self):
        """Validate implementation quality metrics."""

        print("\n🎯 VALIDATING IMPLEMENTATION QUALITY")
        print("-" * 40)

        # Calculate quality metrics
        valid_files = len([r for r in self.validation_results if r["valid"]])
        total_files = len(self.validation_results)
        file_quality_score = (valid_files / total_files * 100) if total_files > 0 else 0

        passed_tests = len([t for t in self.test_results if t["passed"]])
        total_tests = len(self.test_results)
        test_quality_score = (
            (passed_tests / total_tests * 100) if total_tests > 0 else 0
        )

        # Overall quality score
        overall_quality = (file_quality_score + test_quality_score) / 2

        print(
            f"  📁 File Quality: {file_quality_score:.1f}% ({valid_files}/{total_files})"
        )
        print(
            f"  🧪 Test Quality: {test_quality_score:.1f}% ({passed_tests}/{total_tests})"
        )
        print(f"  🎯 Overall Quality: {overall_quality:.1f}%")

        # Quality assessment
        if overall_quality >= 90:
            quality_level = "EXCELLENT"
        elif overall_quality >= 80:
            quality_level = "GOOD"
        elif overall_quality >= 70:
            quality_level = "ACCEPTABLE"
        else:
            quality_level = "NEEDS IMPROVEMENT"

        print(f"  🏆 Quality Level: {quality_level}")

    def _generate_validation_report(self):
        """Generate comprehensive validation report."""

        print("\n📊 GENERATING VALIDATION REPORT")
        print("-" * 40)

        # Calculate summary statistics
        valid_files = len([r for r in self.validation_results if r["valid"]])
        total_files = len(self.validation_results)
        passed_tests = len([t for t in self.test_results if t["passed"]])
        total_tests = len(self.test_results)

        report = {
            "validation_date": datetime.now().isoformat(),
            "summary": {
                "total_files_validated": total_files,
                "valid_files": valid_files,
                "file_validation_rate": (valid_files / total_files * 100)
                if total_files > 0
                else 0,
                "total_tests_run": total_tests,
                "passed_tests": passed_tests,
                "test_success_rate": (passed_tests / total_tests * 100)
                if total_tests > 0
                else 0,
                "overall_quality_score": (
                    (valid_files / total_files * 100)
                    + (passed_tests / total_tests * 100)
                )
                / 2
                if total_files > 0 and total_tests > 0
                else 0,
            },
            "file_validation_results": self.validation_results,
            "test_results": self.test_results,
            "recommendations": self._generate_recommendations(),
        }

        # Save report
        report_path = self.base_path / "refactoring_validation_report.yaml"
        with open(report_path, "w") as f:
            yaml.dump(report, f, default_flow_style=False, sort_keys=False)

        print(f"💾 Validation report saved: {report_path}")

        # Display final summary
        self._display_final_summary(report)

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on validation results."""

        recommendations = []

        # File validation recommendations
        invalid_files = [r for r in self.validation_results if not r["valid"]]
        if invalid_files:
            recommendations.append(
                f"Fix {len(invalid_files)} invalid files: {[f['file'] for f in invalid_files]}"
            )

        # Test recommendations
        failed_tests = [t for t in self.test_results if not t["passed"]]
        if failed_tests:
            recommendations.append(
                f"Fix {len(failed_tests)} failed tests: {[t['test'] for t in failed_tests]}"
            )

        # General recommendations
        if len(self.validation_results) < 10:
            recommendations.append("Generate more comprehensive file coverage")

        if len(self.test_results) < 5:
            recommendations.append("Expand test coverage for better validation")

        if not recommendations:
            recommendations.append(
                "All validations passed - ready for production deployment"
            )

        return recommendations

    def _display_final_summary(self, report: Dict):
        """Display final validation summary."""

        summary = report["summary"]

        print("\n🎉 FINAL VALIDATION SUMMARY")
        print("=" * 50)

        print(
            f"📁 FILES: {summary['valid_files']}/{summary['total_files_validated']} valid ({summary['file_validation_rate']:.1f}%)"
        )
        print(
            f"🧪 TESTS: {summary['passed_tests']}/{summary['total_tests_run']} passed ({summary['test_success_rate']:.1f}%)"
        )
        print(f"🎯 OVERALL QUALITY: {summary['overall_quality_score']:.1f}%")

        print("\n📋 RECOMMENDATIONS:")
        for i, rec in enumerate(report["recommendations"], 1):
            print(f"  {i}. {rec}")

        # Final status
        if summary["overall_quality_score"] >= 90:
            status = "🏆 EXCELLENT - Ready for production"
        elif summary["overall_quality_score"] >= 80:
            status = "✅ GOOD - Ready with minor improvements"
        elif summary["overall_quality_score"] >= 70:
            status = "⚠️  ACCEPTABLE - Needs some improvements"
        else:
            status = "❌ NEEDS WORK - Significant improvements required"

        print(f"\n🚀 FINAL STATUS: {status}")
        print("\n🎉 COMPLETE REFACTORING PIPELINE VALIDATED!")


def main():
    """Main validation function."""

    base_path = "."
    validator = RefactoringValidator(base_path)

    try:
        validator.run_complete_validation()

    except Exception as e:
        print(f"❌ Error during validation: {e}")


if __name__ == "__main__":
    main()
