use rand::SeedableRng;
use rand::rngs::StdRng;
use rand::seq::IndexedRandom;

use crate::board::{Board, EdgeCoordinate, VertexCoordinate};
use crate::simulator::{Player, PriorPlacement};

/// Picks a legal town-and-road pair uniformly.
#[derive(Clone)]
pub struct RandomPlayer {
    rng: StdRng,
}

impl RandomPlayer {
    pub fn from_seed(seed: u64) -> Self {
        Self {
            rng: StdRng::seed_from_u64(seed),
        }
    }
}

impl Player for RandomPlayer {
    fn choose(
        &mut self,
        _board: &Board,
        available: &[(VertexCoordinate, EdgeCoordinate)],
        _prior: &[PriorPlacement],
        _errors: &[String],
    ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
        available
            .choose(&mut self.rng)
            .copied()
            .ok_or_else(|| "no legal placement".to_string())
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::*;
    use crate::simulator::Simulator;
    use crate::{EdgeCoordinate, Index, VertexCoordinate};

    fn pair(q: i8, index: Index) -> (VertexCoordinate, EdgeCoordinate) {
        (
            VertexCoordinate::new(q, 0, index),
            EdgeCoordinate::new(q, 0, index),
        )
    }

    fn draft(seed: u64, seats: usize) -> crate::Report {
        let players = (0..seats)
            .map(|seat| {
                Box::new(RandomPlayer::from_seed(seed.wrapping_add(seat as u64))) as Box<dyn Player>
            })
            .collect();
        let mut simulator = Simulator::new(Board::from_seed(seed), players).unwrap();
        simulator.simulate(1)
    }

    #[test]
    fn only_pair_is_always_chosen() {
        let only = pair(0, Index::Zero);
        let mut player = RandomPlayer::from_seed(1);
        let board = Board::from_seed(0);
        assert_eq!(player.choose(&board, &[only], &[], &[]), Ok(only));
    }

    #[test]
    fn empty_list_is_an_error() {
        let mut player = RandomPlayer::from_seed(1);
        let board = Board::from_seed(0);
        assert_eq!(
            player.choose(&board, &[], &[], &[]),
            Err("no legal placement".to_string())
        );
    }

    #[test]
    fn either_pair_can_be_selected() {
        let pairs = [pair(0, Index::Zero), pair(1, Index::One)];
        let board = Board::from_seed(0);
        let mut seen = HashSet::new();
        for seed in 0..64 {
            let mut player = RandomPlayer::from_seed(seed);
            seen.insert(player.choose(&board, &pairs, &[], &[]).unwrap());
        }
        assert_eq!(seen.len(), 2);
    }

    #[test]
    fn same_seed_replays_the_draft() {
        for seats in [3, 4] {
            let first = draft(7, seats);
            let second = draft(7, seats);
            assert_eq!(first, second);
            assert!(
                first
                    .errors
                    .iter()
                    .all(|seat_errors| seat_errors.is_empty())
            );
            assert!(first.placements.iter().flatten().all(|slot| slot.is_some()));
        }
    }
}
