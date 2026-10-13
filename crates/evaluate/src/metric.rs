use serde::Serialize;
use serde_json::{Map, Value};

use crate::game::Game;

/// A placement heuristic checked once per seat in a JSONL line.
pub trait Metric {
    fn name(&self) -> &'static str;

    /// Whether one seat's final settlements satisfy the heuristic.
    fn verify(&self, game: &Game, seat: usize) -> bool;
}

#[derive(Debug, Clone, PartialEq)]
pub struct MetricReport {
    pub name: &'static str,
    /// `passed[game][seat]` for every seat in a finished game.
    /// An unfinished game contributes an empty list so it is left out of totals.
    pub passed: Vec<Vec<bool>>,
}

/// One game's heuristic results, line-aligned with a choices JSONL row.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct GameEvaluation {
    pub players: Vec<String>,
    /// Metric name → pass/fail per seat, in registry order.
    /// `None` when the draft did not finish and the heuristics were not computed.
    pub metrics: Option<Map<String, Value>>,
}

pub fn verify_games(games: &[Game], metrics: &[Box<dyn Metric>]) -> Vec<MetricReport> {
    metrics
        .iter()
        .map(|metric| {
            let passed: Vec<Vec<bool>> = games
                .iter()
                .map(|game| {
                    if !game.is_finished() {
                        return Vec::new();
                    }
                    (0..game.choices.len())
                        .map(|seat| metric.verify(game, seat))
                        .collect()
                })
                .collect();
            MetricReport {
                name: metric.name(),
                passed,
            }
        })
        .collect()
}

/// Pivots metric-major reports into one [`GameEvaluation`] per game.
pub fn evaluations(games: &[Game], reports: &[MetricReport]) -> Vec<GameEvaluation> {
    games
        .iter()
        .enumerate()
        .map(|(game_index, game)| {
            let players: Vec<String> = game
                .choices
                .iter()
                .map(|seat| {
                    seat.iter()
                        .flatten()
                        .next()
                        .map(|choice| choice.player.clone())
                        .unwrap_or_default()
                })
                .collect();
            if !game.is_finished() {
                return GameEvaluation {
                    players,
                    metrics: None,
                };
            }
            let mut metrics = Map::new();
            for report in reports {
                let seats = report.passed[game_index]
                    .iter()
                    .copied()
                    .map(Value::Bool)
                    .collect();
                metrics.insert(report.name.to_string(), Value::Array(seats));
            }
            GameEvaluation {
                players,
                metrics: Some(metrics),
            }
        })
        .collect()
}
