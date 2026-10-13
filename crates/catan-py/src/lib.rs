use catan_simulation::{
    Board as SimBoard, ConfigError, EdgeCoordinate, Harbour as SimHarbour, HarbourKind,
    HexCoordinate, Index, Player, PriorPlacement, RandomPlayer as SimRandomPlayer,
    Report as SimReport, Resource, Simulator as SimSimulator, Terrain, Tile as SimTile,
    VertexCoordinate,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyList, PyTuple};

#[pyclass(frozen, eq, hash, from_py_object)]
#[derive(Clone, PartialEq, Eq, Hash)]
struct Vertex {
    inner: VertexCoordinate,
}

#[pymethods]
impl Vertex {
    #[new]
    fn new(q: i8, r: i8, index: u8) -> PyResult<Self> {
        Ok(Self {
            inner: VertexCoordinate::new(q, r, index_from_u8(index)?),
        })
    }

    #[getter]
    fn q(&self) -> i8 {
        self.inner.q
    }

    #[getter]
    fn r(&self) -> i8 {
        self.inner.r
    }

    #[getter]
    fn index(&self) -> u8 {
        index_to_u8(self.inner.index)
    }

    fn __repr__(&self) -> String {
        format!("Vertex({}, {}, {})", self.q(), self.r(), self.index())
    }

    fn hexes(&self) -> Vec<Hex> {
        self.inner.hexes().into_iter().map(Hex::from_sim).collect()
    }
}

#[pyclass(frozen, eq, hash, from_py_object)]
#[derive(Clone, PartialEq, Eq, Hash)]
struct Edge {
    inner: EdgeCoordinate,
}

#[pymethods]
impl Edge {
    #[new]
    fn new(q: i8, r: i8, index: u8) -> PyResult<Self> {
        Ok(Self {
            inner: EdgeCoordinate::new(q, r, index_from_u8(index)?),
        })
    }

    #[getter]
    fn q(&self) -> i8 {
        self.inner.q
    }

    #[getter]
    fn r(&self) -> i8 {
        self.inner.r
    }

    #[getter]
    fn index(&self) -> u8 {
        index_to_u8(self.inner.index)
    }

    fn __repr__(&self) -> String {
        format!("Edge({}, {}, {})", self.q(), self.r(), self.index())
    }

    fn vertices(&self) -> Vec<Vertex> {
        self.inner
            .vertices()
            .into_iter()
            .map(|inner| Vertex { inner })
            .collect()
    }
}

#[pyclass]
struct Hex {
    q: i8,
    r: i8,
}

#[pymethods]
impl Hex {
    #[getter]
    fn q(&self) -> i8 {
        self.q
    }

    #[getter]
    fn r(&self) -> i8 {
        self.r
    }

    fn __repr__(&self) -> String {
        format!("Hex({}, {})", self.q, self.r)
    }
}

#[pyclass]
struct Tile {
    q: i8,
    r: i8,
    number: u8,
    terrain: &'static str,
}

#[pymethods]
impl Tile {
    #[getter]
    fn q(&self) -> i8 {
        self.q
    }

    #[getter]
    fn r(&self) -> i8 {
        self.r
    }

    #[getter]
    fn number(&self) -> u8 {
        self.number
    }

    #[getter]
    fn terrain(&self) -> &str {
        self.terrain
    }

    fn __repr__(&self) -> String {
        format!(
            "Tile({}, {}, {}, {:?})",
            self.q, self.r, self.number, self.terrain
        )
    }
}

impl Tile {
    fn from_sim(tile: SimTile) -> Self {
        Self {
            q: tile.q,
            r: tile.r,
            number: tile.number,
            terrain: terrain_name(tile.terrain),
        }
    }
}

#[pyclass]
struct Harbour {
    edge: EdgeCoordinate,
    kind: &'static str,
}

#[pymethods]
impl Harbour {
    #[getter]
    fn edge(&self) -> Edge {
        Edge { inner: self.edge }
    }

    #[getter]
    fn kind(&self) -> &str {
        self.kind
    }

    fn __repr__(&self) -> String {
        format!("Harbour({}, {:?})", self.edge().__repr__(), self.kind)
    }
}

impl Harbour {
    fn from_sim(harbour: SimHarbour) -> Self {
        Self {
            edge: harbour.edge,
            kind: harbour_kind(harbour.kind),
        }
    }
}

#[pyclass]
struct Board {
    inner: SimBoard,
}

#[pymethods]
impl Board {
    #[staticmethod]
    fn from_seed(seed: u64) -> Self {
        Self {
            inner: SimBoard::from_seed(seed),
        }
    }

    #[getter]
    fn tiles(&self) -> Vec<Tile> {
        self.inner.tiles.into_iter().map(Tile::from_sim).collect()
    }

    #[getter]
    fn desert(&self) -> Hex {
        Hex::from_sim(self.inner.desert)
    }

    #[getter]
    fn harbours(&self) -> Vec<Harbour> {
        self.inner
            .harbours
            .into_iter()
            .map(Harbour::from_sim)
            .collect()
    }

    fn __repr__(&self) -> String {
        format!(
            "Board(tiles={}, desert={})",
            self.inner.tiles.len(),
            Hex::from_sim(self.inner.desert).__repr__()
        )
    }
}

impl Hex {
    fn from_sim(hex: HexCoordinate) -> Self {
        Self { q: hex.q, r: hex.r }
    }
}

#[pyclass(from_py_object)]
#[derive(Clone)]
struct RandomPlayer {
    inner: SimRandomPlayer,
}

#[pymethods]
impl RandomPlayer {
    #[staticmethod]
    fn from_seed(seed: u64) -> Self {
        Self {
            inner: SimRandomPlayer::from_seed(seed),
        }
    }

    fn __repr__(&self) -> &'static str {
        "RandomPlayer()"
    }
}

struct CallablePlayer {
    object: Py<PyAny>,
}

impl Player for CallablePlayer {
    fn choose(
        &mut self,
        board: &SimBoard,
        available: &[(VertexCoordinate, EdgeCoordinate)],
        prior: &[PriorPlacement],
        errors: &[String],
    ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
        Python::attach(|py| call_player(py, &self.object, board, available, prior, errors))
    }
}

#[pyclass(unsendable)]
struct Simulator {
    inner: SimSimulator,
}

#[pymethods]
impl Simulator {
    #[new]
    fn new(py: Python<'_>, board: &Board, players: Vec<Py<PyAny>>) -> PyResult<Self> {
        let mut owned = Vec::with_capacity(players.len());
        for player in players {
            let bound = player.bind(py);
            if bound.is_instance_of::<RandomPlayer>() {
                let random = bound.cast::<RandomPlayer>()?;
                owned.push(Box::new(random.borrow().inner.clone()) as Box<dyn Player>);
            } else {
                owned.push(Box::new(CallablePlayer { object: player }) as Box<dyn Player>);
            }
        }
        match SimSimulator::new(board.inner.clone(), owned) {
            Ok(inner) => Ok(Self { inner }),
            Err(ConfigError::InvalidPlayerCount) => {
                Err(PyValueError::new_err("expected 3 or 4 players"))
            }
        }
    }

    fn simulate(&mut self, max_errors: usize) -> Report {
        Report::from_sim(self.inner.simulate(max_errors))
    }
}

#[pyclass]
struct Report {
    errors: Vec<Vec<String>>,
    placements: Vec<[Option<(VertexCoordinate, EdgeCoordinate)>; 2]>,
}

#[pymethods]
impl Report {
    #[getter]
    fn errors(&self) -> Vec<Vec<String>> {
        self.errors.clone()
    }

    #[getter]
    fn placements<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let seats = PyList::empty(py);
        for seat in &self.placements {
            let first = placement_object(py, seat[0])?;
            let second = placement_object(py, seat[1])?;
            seats.append((first, second))?;
        }
        Ok(seats)
    }
}

impl Report {
    fn from_sim(report: SimReport) -> Self {
        Self {
            errors: report.errors,
            placements: report.placements,
        }
    }
}

fn call_player(
    py: Python<'_>,
    object: &Py<PyAny>,
    board: &SimBoard,
    available: &[(VertexCoordinate, EdgeCoordinate)],
    prior: &[PriorPlacement],
    errors: &[String],
) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
    let result = (|| -> PyResult<_> {
        let board = Py::new(
            py,
            Board {
                inner: board.clone(),
            },
        )?;
        let pairs = PyList::empty(py);
        for &(vertex, edge) in available {
            pairs.append((
                Py::new(py, Vertex { inner: vertex })?,
                Py::new(py, Edge { inner: edge })?,
            ))?;
        }
        let previous = PyList::empty(py);
        for placement in prior {
            previous.append((
                placement.seat,
                Py::new(
                    py,
                    Vertex {
                        inner: placement.vertex,
                    },
                )?,
                Py::new(
                    py,
                    Edge {
                        inner: placement.edge,
                    },
                )?,
            ))?;
        }
        let messages = PyList::new(py, errors.to_vec())?;
        let player = object.bind(py);
        let value = if player.hasattr("choose")? {
            let method = player.getattr("choose")?;
            if method.is_callable() {
                method.call1((board, pairs, previous, messages))?
            } else {
                player.call1((board, pairs, previous, messages))?
            }
        } else {
            player.call1((board, pairs, previous, messages))?
        };
        parse_choice(&value)
    })();
    result.map_err(|err| error_message(py, err))
}

fn parse_choice(value: &Bound<'_, PyAny>) -> PyResult<(VertexCoordinate, EdgeCoordinate)> {
    let vertex: PyRef<Vertex> = value.get_item(0)?.extract()?;
    let edge: PyRef<Edge> = value.get_item(1)?.extract()?;
    Ok((vertex.inner, edge.inner))
}

fn placement_object(
    py: Python<'_>,
    placement: Option<(VertexCoordinate, EdgeCoordinate)>,
) -> PyResult<Py<PyAny>> {
    match placement {
        None => Ok(py.None()),
        Some((vertex, edge)) => {
            let pair = PyTuple::new(
                py,
                [
                    Py::new(py, Vertex { inner: vertex })?.into_any(),
                    Py::new(py, Edge { inner: edge })?.into_any(),
                ],
            )?;
            Ok(pair.unbind().into_any())
        }
    }
}

fn error_message(py: Python<'_>, err: PyErr) -> String {
    match err.value(py).str() {
        Ok(text) => text.to_string_lossy().into_owned(),
        Err(str_err) => {
            let _ = PyErr::take(py);
            str_err.to_string()
        }
    }
}

fn index_from_u8(index: u8) -> PyResult<Index> {
    match index {
        0 => Ok(Index::Zero),
        1 => Ok(Index::One),
        2 => Ok(Index::Two),
        3 => Ok(Index::Three),
        4 => Ok(Index::Four),
        5 => Ok(Index::Five),
        _ => Err(PyValueError::new_err("index must be from 0 to 5")),
    }
}

fn index_to_u8(index: Index) -> u8 {
    match index {
        Index::Zero => 0,
        Index::One => 1,
        Index::Two => 2,
        Index::Three => 3,
        Index::Four => 4,
        Index::Five => 5,
    }
}

fn terrain_name(terrain: Terrain) -> &'static str {
    match terrain {
        Terrain::Forest => "forest",
        Terrain::Pasture => "pasture",
        Terrain::Fields => "fields",
        Terrain::Hills => "hills",
        Terrain::Mountains => "mountains",
    }
}

fn resource_name(resource: Resource) -> &'static str {
    match resource {
        Resource::Brick => "brick",
        Resource::Wood => "wood",
        Resource::Sheep => "sheep",
        Resource::Wheat => "wheat",
        Resource::Ore => "ore",
    }
}

fn harbour_kind(kind: HarbourKind) -> &'static str {
    match kind {
        HarbourKind::Generic => "generic",
        HarbourKind::Specific(resource) => resource_name(resource),
    }
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Vertex>()?;
    module.add_class::<Edge>()?;
    module.add_class::<Hex>()?;
    module.add_class::<Tile>()?;
    module.add_class::<Harbour>()?;
    module.add_class::<Board>()?;
    module.add_class::<RandomPlayer>()?;
    module.add_class::<Simulator>()?;
    module.add_class::<Report>()?;
    Ok(())
}
