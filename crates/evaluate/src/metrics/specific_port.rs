use catan_simulation::{HarbourKind, VertexCoordinate};

use crate::game::Game;
use crate::metric::Metric;
use crate::placement::{distances, port_distance, yields_of};

/// Closest to a 2:1 port for a resource produced on 5, 6, 8, or 9.
pub struct SpecificPort;

impl Metric for SpecificPort {
    fn name(&self) -> &'static str {
        "specific_port"
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
        let mine_dist = distances(&mine);

        for harbour in &game.board.harbours {
            let HarbourKind::Specific(resource) = harbour.kind else {
                continue;
            };
            let useful = yields
                .iter()
                .any(|item| item.resource == resource && matches!(item.number, 5 | 6 | 8 | 9));
            if !useful {
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
    use catan_simulation::{HarbourKind, Resource, Terrain, VertexCoordinate};

    use super::*;
    use crate::placement::{board_with, game_from};

    #[test]
    fn matching_port_on_strong_numbers_passes() {
        let board = board_with(&[]);
        let [port, _] = ore_corners(&board);
        let mut board = board;
        paint(&mut board, port, Terrain::Mountains, 8);
        let game = game_from(board, &[vec![port]]);
        assert!(SpecificPort.verify(&game, 0));
    }

    #[test]
    fn farther_seat_loses_to_someone_on_the_port() {
        let board = board_with(&[]);
        let [port, _] = ore_corners(&board);
        let far = farthest(port);
        let mut board = board;
        paint(&mut board, port, Terrain::Mountains, 8);
        paint(&mut board, far, Terrain::Mountains, 8);
        let game = game_from(board, &[vec![far], vec![port]]);
        assert!(!SpecificPort.verify(&game, 0));
        assert!(SpecificPort.verify(&game, 1));
    }

    #[test]
    fn weak_numbers_do_not_count() {
        let board = board_with(&[]);
        let [port, _] = ore_corners(&board);
        let mut board = board;
        paint(&mut board, port, Terrain::Mountains, 3);
        let game = game_from(board, &[vec![port]]);
        assert!(!SpecificPort.verify(&game, 0));
    }

    fn ore_corners(board: &catan_simulation::Board) -> [VertexCoordinate; 2] {
        board
            .harbours
            .iter()
            .find(|harbour| harbour.kind == HarbourKind::Specific(Resource::Ore))
            .expect("ore port")
            .edge
            .vertices()
    }

    fn farthest(port: VertexCoordinate) -> VertexCoordinate {
        distances(&[port])
            .into_iter()
            .filter(|(vertex, _)| *vertex != port)
            .max_by_key(|(_, roads)| *roads)
            .map(|(vertex, _)| vertex)
            .expect("another intersection")
    }

    fn paint(
        board: &mut catan_simulation::Board,
        vertex: VertexCoordinate,
        terrain: Terrain,
        number: u8,
    ) {
        for hex in vertex.hexes() {
            if let Some(tile) = board
                .tiles
                .iter_mut()
                .find(|tile| tile.q == hex.q && tile.r == hex.r)
            {
                tile.terrain = terrain;
                tile.number = number;
            }
        }
    }
}
