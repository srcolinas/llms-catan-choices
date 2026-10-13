use catan_simulation::{Resource, VertexCoordinate};

use crate::game::Game;
use crate::metric::Metric;
use crate::placement::yields_of;

/// Ore/wheat or wood/brick across the seat's final settlements.
pub struct ResourceCombos;

impl Metric for ResourceCombos {
    fn name(&self) -> &'static str {
        "resource_combos"
    }

    fn verify(&self, game: &Game, seat: usize) -> bool {
        let vertices: Vec<VertexCoordinate> = game.choices[seat]
            .iter()
            .flatten()
            .map(|choice| {
                VertexCoordinate::new(choice.vertex.q, choice.vertex.r, choice.vertex.index)
            })
            .collect();
        let yields = yields_of(&game.board, &vertices);
        let mut has_ore = false;
        let mut has_wheat = false;
        let mut has_wood = false;
        let mut has_brick = false;
        for item in yields {
            match item.resource {
                Resource::Ore => has_ore = true,
                Resource::Wheat => has_wheat = true,
                Resource::Wood => has_wood = true,
                Resource::Brick => has_brick = true,
                Resource::Sheep => {}
            }
        }
        (has_ore && has_wheat) || (has_wood && has_brick)
    }
}

#[cfg(test)]
mod tests {
    use catan_simulation::{Index, Terrain, VertexCoordinate};

    use super::*;
    use crate::placement::{board_with, game_from};

    #[test]
    fn city_pair_on_one_settlement_passes() {
        let game = game_from(
            board_with(&[
                ((0, 0), 6, Terrain::Mountains),
                ((1, 0), 8, Terrain::Fields),
                ((1, -1), 4, Terrain::Hills),
            ]),
            &[vec![VertexCoordinate::new(0, 0, Index::One)]],
        );
        assert!(ResourceCombos.verify(&game, 0));
    }

    #[test]
    fn wood_and_brick_on_separate_settlements_pass() {
        let game = game_from(
            board_with(&[
                ((0, 0), 5, Terrain::Forest),
                ((1, 0), 3, Terrain::Pasture),
                ((1, -1), 2, Terrain::Pasture),
                ((0, 2), 9, Terrain::Hills),
                ((-1, 2), 4, Terrain::Pasture),
                ((-1, 1), 11, Terrain::Pasture),
            ]),
            &[vec![
                VertexCoordinate::new(0, 0, Index::One),
                VertexCoordinate::new(0, 2, Index::Zero),
            ]],
        );
        assert!(ResourceCombos.verify(&game, 0));
    }

    #[test]
    fn sheep_only_fails() {
        let game = game_from(
            board_with(&[
                ((0, 0), 6, Terrain::Pasture),
                ((1, 0), 8, Terrain::Pasture),
                ((1, -1), 5, Terrain::Pasture),
            ]),
            &[vec![VertexCoordinate::new(0, 0, Index::One)]],
        );
        assert!(!ResourceCombos.verify(&game, 0));
    }
}
