//! Geometry shared by the placement heuristics.
//!
//! Checks look at each seat's final settlements, not turn-by-turn averages.

use std::collections::{HashMap, VecDeque};
use std::sync::OnceLock;

use catan_simulation::{Board, Harbour, Resource, VertexCoordinate, vertex_neighbors};

/// One producing tile touching a settlement.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct Yield {
    pub resource: Resource,
    pub number: u8,
}

pub(crate) fn yields_at(board: &Board, vertex: VertexCoordinate) -> Vec<Yield> {
    let vertex = VertexCoordinate::new(vertex.q, vertex.r, vertex.index);
    let mut yields = Vec::new();
    for hex in vertex.hexes() {
        let Some(tile) = board
            .tiles
            .iter()
            .find(|tile| tile.q == hex.q && tile.r == hex.r)
        else {
            continue;
        };
        if !matches!(tile.number, 2..=6 | 8..=12) {
            continue;
        }
        yields.push(Yield {
            resource: tile.terrain.resource(),
            number: tile.number,
        });
    }
    yields
}

pub(crate) fn yields_of(board: &Board, vertices: &[VertexCoordinate]) -> Vec<Yield> {
    vertices
        .iter()
        .flat_map(|vertex| yields_at(board, *vertex))
        .collect()
}

fn adjacency() -> &'static HashMap<VertexCoordinate, Vec<VertexCoordinate>> {
    static ADJACENCY: OnceLock<HashMap<VertexCoordinate, Vec<VertexCoordinate>>> = OnceLock::new();
    ADJACENCY.get_or_init(vertex_neighbors)
}

pub(crate) fn distances(starts: &[VertexCoordinate]) -> HashMap<VertexCoordinate, u32> {
    let mut distance = HashMap::new();
    let mut queue = VecDeque::new();
    for &start in starts {
        if adjacency().contains_key(&start) && distance.insert(start, 0).is_none() {
            queue.push_back(start);
        }
    }
    while let Some(current) = queue.pop_front() {
        let next = distance[&current] + 1;
        for &neighbor in &adjacency()[&current] {
            if distance.contains_key(&neighbor) {
                continue;
            }
            distance.insert(neighbor, next);
            queue.push_back(neighbor);
        }
    }
    distance
}

pub(crate) fn port_distance(
    distance: &HashMap<VertexCoordinate, u32>,
    harbour: &Harbour,
) -> Option<u32> {
    harbour
        .edge
        .vertices()
        .into_iter()
        .filter_map(|vertex| distance.get(&vertex).copied())
        .min()
}

#[cfg(test)]
pub(crate) fn board_with(updates: &[((i8, i8), u8, catan_simulation::Terrain)]) -> Board {
    use std::collections::HashSet;

    let mut board = Board::from_seed(1);
    let wanted: HashSet<(i8, i8)> = updates.iter().map(|(position, _, _)| *position).collect();
    let positions: Vec<(i8, i8)> = wanted.iter().copied().collect();
    for (q, r) in positions {
        if board.tiles.iter().any(|tile| tile.q == q && tile.r == r) {
            continue;
        }
        assert_eq!(
            (board.desert.q, board.desert.r),
            (q, r),
            "hex ({q}, {r}) is not on the island"
        );
        let donor = board
            .tiles
            .iter_mut()
            .find(|tile| !wanted.contains(&(tile.q, tile.r)))
            .expect("a numbered hex outside the update set");
        let freed = catan_simulation::HexCoordinate {
            q: donor.q,
            r: donor.r,
        };
        donor.q = q;
        donor.r = r;
        board.desert = freed;
    }
    for &((q, r), number, terrain) in updates {
        let tile = board
            .tiles
            .iter_mut()
            .find(|tile| tile.q == q && tile.r == r)
            .expect("updated hex is a tile");
        tile.number = number;
        tile.terrain = terrain;
    }
    board
}

#[cfg(test)]
pub(crate) fn game_from(board: Board, seats: &[Vec<VertexCoordinate>]) -> crate::game::Game {
    use catan_simulation::EdgeCoordinate;

    use crate::game::{Choice, Game};

    fn choice_at(vertex: VertexCoordinate) -> Choice {
        let vertex = VertexCoordinate::new(vertex.q, vertex.r, vertex.index);
        Choice {
            kind: String::new(),
            player: String::new(),
            vertex,
            edge: EdgeCoordinate::new(vertex.q, vertex.r, vertex.index),
        }
    }

    Game {
        board,
        choices: seats
            .iter()
            .map(|seat| {
                seat.iter()
                    .copied()
                    .map(|vertex| Some(choice_at(vertex)))
                    .collect()
            })
            .collect(),
    }
}
