use std::collections::HashSet;

use catan_simulation::VertexCoordinate;

use crate::game::Game;
use crate::metric::Metric;
use crate::placement::yields_of;

/// Four different numbers from 4, 5, 6, 8, 9, and 10 across both settlements.
pub struct Production;

impl Metric for Production {
    fn name(&self) -> &'static str {
        "production"
    }

    fn verify(&self, game: &Game, seat: usize) -> bool {
        let vertices: Vec<VertexCoordinate> = game.choices[seat]
            .iter()
            .flatten()
            .map(|choice| {
                VertexCoordinate::new(choice.vertex.q, choice.vertex.r, choice.vertex.index)
            })
            .collect();
        let numbers = yields_of(&game.board, &vertices)
            .into_iter()
            .filter(|item| matches!(item.number, 4 | 5 | 6 | 8 | 9 | 10))
            .map(|item| item.number)
            .collect::<HashSet<_>>();
        numbers.len() >= 4
    }
}

#[cfg(test)]
mod tests {
    use catan_simulation::{Board, HexCoordinate, Index, Terrain, VertexCoordinate};

    use super::*;
    use crate::placement::{board_with, game_from};

    /// `(0, 0, 1)` and `(0, 2, 0)` each touch three land hexes, and those hexes do not overlap.
    fn passes(settlements: &[[u8; 3]]) -> bool {
        let corners = [
            VertexCoordinate::new(0, 0, Index::One),
            VertexCoordinate::new(0, 2, Index::Zero),
        ];
        let probe = Board::from_seed(1);
        let mut updates = Vec::new();
        let vertices: Vec<_> = settlements
            .iter()
            .enumerate()
            .map(|(index, numbers)| {
                let vertex = corners[index];
                let land = land_hexes(&probe, vertex);
                assert_eq!(land.len(), 3, "settlement {index} should touch three tiles");
                for (hex, number) in land.into_iter().zip(*numbers) {
                    updates.push(((hex.q, hex.r), number, Terrain::Pasture));
                }
                vertex
            })
            .collect();
        let game = game_from(board_with(&updates), &[vertices]);
        Production.verify(&game, 0)
    }

    fn land_hexes(board: &Board, vertex: VertexCoordinate) -> Vec<HexCoordinate> {
        vertex
            .hexes()
            .into_iter()
            .filter(|hex| {
                board
                    .tiles
                    .iter()
                    .any(|tile| tile.q == hex.q && tile.r == hex.r)
                    || (board.desert.q == hex.q && board.desert.r == hex.r)
            })
            .collect()
    }

    #[test]
    fn four_good_numbers_across_settlements_pass() {
        assert!(passes(&[[5, 6, 9], [4, 8, 8]]));
    }

    #[test]
    fn five_good_numbers_pass() {
        assert!(passes(&[[4, 5, 6], [8, 9, 10]]));
    }

    #[test]
    fn rare_number_beside_four_good_numbers_still_passes() {
        assert!(passes(&[[4, 5, 6], [8, 2, 12]]));
    }

    #[test]
    fn three_good_numbers_fail() {
        assert!(!passes(&[[5, 6, 9]]));
    }

    #[test]
    fn repeated_numbers_fail() {
        assert!(!passes(&[[6, 6, 9], [6, 8, 8]]));
    }

    #[test]
    fn rare_numbers_do_not_count() {
        assert!(!passes(&[[2, 3, 11], [12, 4, 5]]));
    }
}
