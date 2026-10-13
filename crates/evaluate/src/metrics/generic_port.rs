use catan_simulation::{HarbourKind, Resource, VertexCoordinate};

use crate::game::Game;
use crate::metric::Metric;
use crate::placement::{distances, port_distance, yields_of};

/// Closest to a 3:1 port with two or more focused mid/high numbers of one resource.
pub struct GenericPort;

impl Metric for GenericPort {
    fn name(&self) -> &'static str {
        "generic_port"
    }

    fn verify(&self, game: &Game, seat: usize) -> bool {
        let mine: Vec<VertexCoordinate> = game.choices[seat]
            .iter()
            .flatten()
            .map(|choice| {
                VertexCoordinate::new(choice.vertex.q, choice.vertex.r, choice.vertex.index)
            })
            .collect();
        let yields = yields_of(&game.board, &mine);
        let concentrated = [
            Resource::Brick,
            Resource::Wood,
            Resource::Sheep,
            Resource::Wheat,
            Resource::Ore,
        ]
        .into_iter()
        .any(|resource| {
            yields
                .iter()
                .filter(|item| {
                    item.resource == resource && matches!(item.number, 4 | 5 | 6 | 8 | 9 | 10)
                })
                .count()
                >= 2
        });
        if !concentrated {
            return false;
        }

        let mine_dist = distances(&mine);
        for harbour in &game.board.harbours {
            if harbour.kind != HarbourKind::Generic {
                continue;
            }
            let Some(my_distance) = port_distance(&mine_dist, harbour) else {
                continue;
            };
            let mut closest = true;
            for (other_seat, other_choices) in game.choices.iter().enumerate() {
                if other_seat == seat || other_choices.is_empty() {
                    continue;
                }
                let others: Vec<VertexCoordinate> = other_choices
                    .iter()
                    .flatten()
                    .map(|choice| {
                        VertexCoordinate::new(choice.vertex.q, choice.vertex.r, choice.vertex.index)
                    })
                    .collect();
                let other_dist = distances(&others);
                if let Some(their_distance) = port_distance(&other_dist, harbour)
                    && their_distance < my_distance
                {
                    closest = false;
                    break;
                }
            }
            if closest {
                return true;
            }
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use catan_simulation::{HarbourKind, Terrain, VertexCoordinate};

    use super::*;
    use crate::placement::{board_with, game_from};

    #[test]
    fn concentrated_on_a_generic_port_passes() {
        let board = board_with(&[]);
        let port = generic_corner(&board);
        let mut board = board;
        paint(
            &mut board,
            port,
            &[Terrain::Fields, Terrain::Fields, Terrain::Fields],
            8,
        );
        let game = game_from(board, &[vec![port]]);
        assert!(GenericPort.verify(&game, 0));
    }

    #[test]
    fn mixed_resources_fail() {
        let board = board_with(&[]);
        let port = generic_corner(&board);
        let mut board = board;
        paint(
            &mut board,
            port,
            &[Terrain::Fields, Terrain::Forest, Terrain::Hills],
            8,
        );
        let game = game_from(board, &[vec![port]]);
        assert!(!GenericPort.verify(&game, 0));
    }

    fn generic_corner(board: &catan_simulation::Board) -> VertexCoordinate {
        board
            .harbours
            .iter()
            .filter(|harbour| harbour.kind == HarbourKind::Generic)
            .flat_map(|harbour| harbour.edge.vertices())
            .max_by_key(|vertex| land_hexes(board, *vertex).len())
            .expect("generic port")
    }

    fn land_hexes(
        board: &catan_simulation::Board,
        vertex: VertexCoordinate,
    ) -> Vec<catan_simulation::HexCoordinate> {
        vertex
            .hexes()
            .into_iter()
            .filter(|hex| {
                board
                    .tiles
                    .iter()
                    .any(|tile| tile.q == hex.q && tile.r == hex.r)
            })
            .collect()
    }

    fn paint(
        board: &mut catan_simulation::Board,
        vertex: VertexCoordinate,
        terrains: &[Terrain],
        number: u8,
    ) {
        for (hex, terrain) in land_hexes(board, vertex)
            .into_iter()
            .zip(terrains.iter().cycle())
        {
            let tile = board
                .tiles
                .iter_mut()
                .find(|tile| tile.q == hex.q && tile.r == hex.r)
                .expect("land hex");
            tile.terrain = *terrain;
            tile.number = number;
        }
    }
}
