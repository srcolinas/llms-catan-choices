mod game;
mod metric;
mod metrics;
mod placement;

use std::path::Path;

pub use game::{Choice, Error, Game, read_games, write_jsonl};
pub use metric::{GameEvaluation, Metric, MetricReport, evaluations, verify_games};
pub use metrics::metrics;

pub fn run(path: &Path) -> Result<(Vec<GameEvaluation>, Vec<MetricReport>), Error> {
    let games = read_games(path)?;
    let reports = verify_games(&games, &metrics());
    let rows = evaluations(&games, &reports);
    Ok((rows, reports))
}

pub fn run_and_write(
    input: &Path,
    output: &Path,
) -> Result<(Vec<GameEvaluation>, Vec<MetricReport>), Error> {
    let (rows, reports) = run(input)?;
    write_jsonl(output, &rows)?;
    Ok((rows, reports))
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use catan_simulation::{
        Board, EdgeCoordinate, HarbourKind, HexCoordinate, Index, Resource, Terrain,
        VertexCoordinate,
    };
    use serde_json::Value;

    use crate::game::Choice;
    use crate::metric::{Metric, evaluations, verify_games};
    use crate::{Game, metrics, read_games, run, write_jsonl};

    fn fixture() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/games.jsonl")
    }

    fn sample_game(player: &str) -> Game {
        Game {
            board: Board::from_seed(1),
            choices: vec![vec![Some(Choice {
                kind: String::new(),
                player: player.to_string(),
                vertex: VertexCoordinate {
                    q: 0,
                    r: 0,
                    index: Index::Zero,
                },
                edge: EdgeCoordinate {
                    q: 0,
                    r: 0,
                    index: Index::Zero,
                },
            })]],
        }
    }

    #[test]
    fn fixture_parses_lines_with_and_without_kind() {
        let games = read_games(&fixture()).unwrap();
        assert_eq!(games.len(), 2);

        let omitted = games[0].choices[0][0].as_ref().unwrap();
        assert_eq!(omitted.kind, "");
        assert_eq!(omitted.player, "random");
        assert_eq!(
            omitted.vertex,
            VertexCoordinate {
                q: 2,
                r: -2,
                index: Index::One,
            }
        );
        assert_eq!(games[0].board.desert, HexCoordinate { q: 0, r: -1 });
        assert_eq!(games[0].board.tiles[0].terrain, Terrain::Pasture);
        assert_eq!(games[0].board.tiles[0].number, 5);
        assert_eq!(games[0].board.harbours[0].kind, HarbourKind::Generic);
        assert_eq!(
            games[0].board.harbours[4].kind,
            HarbourKind::Specific(Resource::Wood)
        );

        let present = games[1].choices[0][0].as_ref().unwrap();
        assert_eq!(present.kind, "generative");
        assert_eq!(present.player, "gateway/openai:gpt-6-luna");
        assert_eq!(present.edge.index, Index::One);
    }

    #[test]
    fn read_games_skips_failed_and_malformed_lines() {
        let original = read_games(&fixture()).unwrap();
        let dir = tempfile_dir();
        let input = dir.join("choices.jsonl");
        let failed = r#"{"seed":9,"ok":false,"error":"rate limit","board":{},"choices":[]}"#;
        let body = std::fs::read_to_string(fixture()).unwrap();
        std::fs::write(&input, format!("{failed}\nnot json\n{body}")).unwrap();

        assert_eq!(read_games(&input).unwrap(), original);
    }

    #[test]
    fn choice_metadata_is_ignored() {
        let original = read_games(&fixture()).unwrap();
        let mut rows: Vec<Value> = std::fs::read_to_string(fixture())
            .unwrap()
            .lines()
            .filter(|line| !line.trim().is_empty())
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        for row in &mut rows {
            row["choices"][0][0]["metadata"] = serde_json::json!({ "latency_ms": 842 });
        }
        let dir = tempfile_dir();
        let input = dir.join("choices.jsonl");
        let body = rows
            .iter()
            .map(|row| serde_json::to_string(row).unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        std::fs::write(&input, format!("{body}\n")).unwrap();

        let with_metadata = read_games(&input).unwrap();
        assert_eq!(with_metadata, original);

        let reports = verify_games(&with_metadata, &metrics());
        let scored = evaluations(&with_metadata, &reports);
        assert_eq!(
            scored,
            evaluations(&original, &verify_games(&original, &metrics()))
        );

        let output = dir.join("evaluation.jsonl");
        write_jsonl(&output, &scored).unwrap();
        let written = std::fs::read_to_string(&output).unwrap();
        assert!(!written.contains("latency_ms"));
        assert!(!written.contains("metadata"));
    }

    #[test]
    fn placement_metrics_report_per_seat_booleans() {
        let games = [sample_game("random"), sample_game("random")];
        let reports = verify_games(&games, &metrics());
        assert_eq!(
            reports.iter().map(|report| report.name).collect::<Vec<_>>(),
            [
                "resource_combos",
                "specific_port",
                "generic_port",
                "production",
                "diversity",
            ]
        );
        for report in &reports {
            assert_eq!(report.passed.len(), 2);
            assert_eq!(report.passed[0].len(), 1);
            assert_eq!(report.passed[1].len(), 1);
            assert_eq!(report.passed[0], report.passed[1]);
        }

        let empty = Game {
            board: catan_simulation::Board::from_seed(1),
            choices: Vec::new(),
        };
        let empty_reports = verify_games(&[empty], &metrics());
        assert!(
            empty_reports
                .iter()
                .all(|report| report.passed == vec![Vec::<bool>::new()])
        );

        let fixture_reports = verify_games(&read_games(&fixture()).unwrap(), &metrics());
        assert_eq!(fixture_reports.len(), 5);
        for report in &fixture_reports {
            assert_eq!(report.passed.len(), 2);
            assert_eq!(report.passed[0].len(), 1);
            assert_eq!(report.passed[1].len(), 1);
        }
    }

    #[test]
    fn verify_games_collects_each_seat() {
        struct Always;

        impl Metric for Always {
            fn name(&self) -> &'static str {
                "always"
            }

            fn verify(&self, game: &Game, seat: usize) -> bool {
                game.choices
                    .get(seat)
                    .is_some_and(|choices| !choices.is_empty())
            }
        }

        let reports = verify_games(
            &[sample_game("ab"), sample_game("abcd")],
            &[Box::new(Always)],
        );
        assert_eq!(reports[0].passed, vec![vec![true], vec![true]]);

        let empty = verify_games(&[], &metrics());
        assert!(empty.iter().all(|report| report.passed.is_empty()));
    }

    #[test]
    fn evaluations_line_align_with_players_and_metric_keys() {
        let games = read_games(&fixture()).unwrap();
        let reports = verify_games(&games, &metrics());
        let rows = evaluations(&games, &reports);

        assert_eq!(rows.len(), games.len());
        assert_eq!(rows[0].players, vec!["random".to_string()]);
        assert_eq!(
            rows[1].players,
            vec!["gateway/openai:gpt-6-luna".to_string()]
        );

        let expected_keys = [
            "resource_combos",
            "specific_port",
            "generic_port",
            "production",
            "diversity",
        ];
        for (game_index, row) in rows.iter().enumerate() {
            let metrics = row.metrics.as_ref().expect("finished game");
            let keys: Vec<_> = metrics.keys().map(String::as_str).collect();
            assert_eq!(keys, expected_keys);
            for (name, seats) in metrics {
                let Value::Array(values) = seats else {
                    panic!("metric {name} should be an array");
                };
                assert_eq!(values.len(), games[game_index].choices.len());
                assert!(values.iter().all(|value| value.is_boolean()));
            }
        }

        let empty_game = Game {
            board: Board::from_seed(1),
            choices: Vec::new(),
        };
        let empty_reports = verify_games(std::slice::from_ref(&empty_game), &metrics());
        let empty_eval = evaluations(std::slice::from_ref(&empty_game), &empty_reports);
        assert_eq!(empty_eval.len(), 1);
        assert!(empty_eval[0].players.is_empty());
        let metrics = empty_eval[0]
            .metrics
            .as_ref()
            .expect("empty choices are finished");
        for seats in metrics.values() {
            assert_eq!(seats, &Value::Array(vec![]));
        }
    }

    #[test]
    fn unfinished_draft_has_null_metrics_and_does_not_change_pass_counts() {
        let finished = sample_game("random");
        let mut partial = sample_game("gateway/model");
        partial.choices[0].insert(0, None);
        let alone = verify_games(std::slice::from_ref(&finished), &metrics());
        let games = [finished, partial];
        let reports = verify_games(&games, &metrics());

        assert_eq!(reports.len(), alone.len());
        for (combined, finished_only) in reports.iter().zip(&alone) {
            assert_eq!(combined.passed[0], finished_only.passed[0]);
            assert!(combined.passed[1].is_empty());
        }

        let rows = evaluations(&games, &reports);
        assert!(rows[0].metrics.is_some());
        assert_eq!(rows[1].players, vec!["gateway/model".to_string()]);
        assert!(rows[1].metrics.is_none());
        let serialized = serde_json::to_value(&rows[1]).unwrap();
        assert!(serialized["metrics"].is_null());
    }

    #[test]
    fn run_returns_one_evaluation_per_fixture_line() {
        let (rows, reports) = run(&fixture()).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(reports.len(), 5);
        assert_eq!(rows[0].players, vec!["random"]);
        assert_eq!(rows[1].players, vec!["gateway/openai:gpt-6-luna"]);
    }

    #[test]
    fn run_and_write_emits_jsonl() {
        let dir = tempfile_dir();
        let output = dir.join("evaluation.jsonl");
        let (rows, _) = crate::run_and_write(&fixture(), &output).unwrap();
        let text = std::fs::read_to_string(&output).unwrap();
        let lines: Vec<_> = text.lines().filter(|line| !line.is_empty()).collect();
        assert_eq!(lines.len(), rows.len());
        let first: serde_json::Value = serde_json::from_str(lines[0]).unwrap();
        assert_eq!(first["players"], serde_json::json!(["random"]));
        assert!(first["metrics"]["specific_port"].as_array().is_some());
    }

    fn tempfile_dir() -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "catan-eval-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }
}
