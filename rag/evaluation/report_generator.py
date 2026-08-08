"""Report generator — produces Markdown and JSON evaluation reports."""

import json
from datetime import datetime, timezone
from pathlib import Path
from rag.evaluation.models import EvaluationReport


class ReportGenerator:
    """Generates Markdown and JSON evaluation reports.

    Args:
        output_dir: Directory where reports will be saved.
    """

    def __init__(self, output_dir: str = "rag/evaluation/reports") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_markdown(self, report: EvaluationReport) -> str:
        """Generate a Markdown evaluation report.

        Args:
            report: EvaluationReport with aggregated metrics.

        Returns:
            Path to the generated Markdown file.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "# RAG Retrieval Accuracy Report",
            f"**Generated:** {timestamp}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Queries | {report.total_queries} |",
            f"| Successful Retrievals | {report.successful_retrievals} |",
            f"| Failed Retrievals | {report.failed_retrievals} |",
            f"| Success Rate | {report.success_rate:.1%} |",
            f"| Top-1 Accuracy | {report.top_1_accuracy:.1%} |",
            f"| Top-3 Accuracy | {report.top_3_accuracy:.1%} |",
            f"| Top-5 Accuracy | {report.top_5_accuracy:.1%} |",
            f"| Average Similarity | {report.average_similarity:.3f} |",
            f"| Average Keyword Match Rate | {report.average_keyword_match_rate:.1%} |",
            "",
            "## Failure Analysis",
            "",
        ]

        if report.failure_analysis:
            lines.append("| Failure Type | Count |")
            lines.append("|-------------|-------|")
            for reason, count in sorted(report.failure_analysis.items(), key=lambda x: -x[1]):
                lines.append(f"| {reason} | {count} |")
        else:
            lines.append("No failures detected.")

        lines += [
            "",
            "## Recommendations",
            "",
        ]
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")

        lines += [
            "",
            "## Per-Query Results",
            "",
            "| ID | Category | Question | Hit | Rank | Sim | KW Match |",
            "|----|----------|----------|-----|------|-----|----------|",
        ]

        for r in report.results:
            rank = str(r.first_hit_rank) if r.first_hit_rank else "-"
            hit = "✅" if r.top_k_hit else "❌"
            question = r.query.question[:50] + "..." if len(r.query.question) > 50 else r.query.question
            lines.append(
                f"| {r.query.id} | {r.query.category} | {question} | "
                f"{hit} | {rank} | {r.average_similarity:.2f} | {r.keyword_match_rate:.0%} |"
            )

        lines += [
            "",
            "## Failed Queries",
            "",
        ]
        failed = [r for r in report.results if not r.is_successful]
        if failed:
            for r in failed:
                lines.append(f"### {r.query.id}: {r.query.question}")
                lines.append(f"- **Failures:** {', '.join(r.failure_reasons) or 'none'}")
                lines.append(f"- **Similarity:** {r.average_similarity:.3f}")
                lines.append(f"- **Keywords matched:** {r.keyword_matches}/{len(r.query.expected_keywords)}")
                lines.append("")
        else:
            lines.append("All queries retrieved relevant results.")

        content = "\n".join(lines)
        path = self._output_dir / "retrieval_report.md"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"Markdown report saved: {path}")
        return str(path)

    def generate_json(self, report: EvaluationReport) -> str:
        """Generate a JSON evaluation report.

        Args:
            report: EvaluationReport with aggregated metrics.

        Returns:
            Path to the generated JSON file.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        data = {
            "generated_at": timestamp,
            "summary": {
                "total_queries": report.total_queries,
                "successful_retrievals": report.successful_retrievals,
                "failed_retrievals": report.failed_retrievals,
                "success_rate": round(report.success_rate, 3),
                "top_1_accuracy": round(report.top_1_accuracy, 3),
                "top_3_accuracy": round(report.top_3_accuracy, 3),
                "top_5_accuracy": round(report.top_5_accuracy, 3),
                "average_similarity": round(report.average_similarity, 3),
                "average_keyword_match_rate": round(report.average_keyword_match_rate, 3),
            },
            "failure_analysis": report.failure_analysis,
            "recommendations": report.recommendations,
            "results": [
                {
                    "id": r.query.id,
                    "question": r.query.question,
                    "category": r.query.category,
                    "top_k_hit": r.top_k_hit,
                    "first_hit_rank": r.first_hit_rank,
                    "average_similarity": round(r.average_similarity, 3),
                    "keyword_matches": r.keyword_matches,
                    "keyword_match_rate": round(r.keyword_match_rate, 3),
                    "failure_reasons": r.failure_reasons,
                }
                for r in report.results
            ],
        }

        path = self._output_dir / "retrieval_report.json"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2)
        print(f"JSON report saved: {path}")
        return str(path)
