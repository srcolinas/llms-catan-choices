use std::collections::HashSet;

use catan_simulation::VertexCoordinate;

use crate::game::Game;
use crate::metric::Metric;
use crate::placement::yields_of;

/// Access to at least four resource types across the seat's settlements.
pub struct Diversity;

impl Metric for Diversity {
    fn name(&self) -> &'static str {
        "diversity"
    }

    fn verify(&self, game: &Game, seat: usize) -> bool {
        let vertices: Vec<VertexCoordinate> = game.choices[seat]
            .iter()
            .flatten()
            // The following map is there to ensure the vertices are in canonical form.
            .map(|choice| {
                VertexCoordinate::new(choice.vertex.q, choice.vertex.r, choice.vertex.index)
            })
            .collect();
        let distinct = yields_of(&game.board, &vertices)
            .into_iter()
            .map(|item| item.resource)
            .collect::<HashSet<_>>()
            .len();
        distinct >= 4
    }
}

#[cfg(test)]
mod tests {
    use catan_simulation::{Index, Terrain, VertexCoordinate};

    use super::*;
    use crate::placement::{board_with, game_from};

    #[test]
    fn four_resources_across_two_settlements_pass() {
        let game = game_from(
            board_with(&[
                ((0, 0), 6, Terrain::Forest),
                ((1, 0), 8, Terrain::Hills),
                ((1, -1), 5, Terrain::Fields),
                ((0, 2), 9, Terrain::Mountains),
                ((-1, 2), 4, Terrain::Pasture),
                ((-1, 1), 3, Terrain::Pasture),
            ]),
            &[vec![
                VertexCoordinate::new(0, 0, Index::One),
                VertexCoordinate::new(0, 2, Index::Zero),
            ]],
        );
        assert!(Diversity.verify(&game, 0));
    }

    #[test]
    fn three_resources_on_one_settlement_fail() {
        let game = game_from(
            board_with(&[
                ((0, 0), 6, Terrain::Forest),
                ((1, 0), 8, Terrain::Hills),
                ((1, -1), 5, Terrain::Fields),
            ]),
            &[vec![VertexCoordinate::new(0, 0, Index::One)]],
        );
        assert!(!Diversity.verify(&game, 0));
    }
}
