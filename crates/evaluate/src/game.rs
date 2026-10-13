use std::fs::File;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use catan_simulation::{Board, EdgeCoordinate, VertexCoordinate};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Choice {
    #[serde(default)]
    pub kind: String,
    pub player: String,
    pub vertex: VertexCoordinate,
    pub edge: EdgeCoordinate,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Game {
    pub board: Board,
    pub choices: Vec<Vec<Option<Choice>>>,
}

impl Game {
    /// Every slot holds a placement. A missing slot is JSON null.
    pub fn is_finished(&self) -> bool {
        self.choices.iter().flatten().all(Option::is_some)
    }
}

#[derive(Debug)]
pub enum Error {
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
    Json {
        line: usize,
        source: serde_json::Error,
    },
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io { path, source } => write!(f, "failed to read {}: {source}", path.display()),
            Self::Json { line, source } => write!(f, "line {line}: {source}"),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            Self::Json { source, .. } => Some(source),
        }
    }
}

/// Reads one [`Game`] per scored row.
///
/// Blank lines, malformed JSON, and rows with `ok: false` are skipped. A row
/// with no `ok` field is scored, including drafts that stopped early.
pub fn read_games(path: &Path) -> Result<Vec<Game>, Error> {
    let file = File::open(path).map_err(|source| Error::Io {
        path: path.to_path_buf(),
        source,
    })?;
    let reader = BufReader::new(file);
    let mut games = Vec::new();
    for (index, line) in reader.lines().enumerate() {
        let line = line.map_err(|source| Error::Io {
            path: path.to_path_buf(),
            source,
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let value: serde_json::Value = match serde_json::from_str(&line) {
            Ok(value) => value,
            Err(_) => continue,
        };
        if value.get("ok") == Some(&serde_json::Value::Bool(false)) {
            continue;
        }
        let game = serde_json::from_value(value).map_err(|source| Error::Json {
            line: index + 1,
            source,
        })?;
        games.push(game);
    }
    Ok(games)
}

/// Writes one JSON object per line.
pub fn write_jsonl<T: Serialize>(path: &Path, rows: &[T]) -> Result<(), Error> {
    let mut file = File::create(path).map_err(|source| Error::Io {
        path: path.to_path_buf(),
        source,
    })?;
    for row in rows {
        let line = serde_json::to_string(row).map_err(|source| Error::Json { line: 0, source })?;
        writeln!(file, "{line}").map_err(|source| Error::Io {
            path: path.to_path_buf(),
            source,
        })?;
    }
    Ok(())
}
