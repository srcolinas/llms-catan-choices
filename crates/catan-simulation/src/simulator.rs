use std::collections::{HashMap, HashSet};

use petgraph::graph::{NodeIndex, UnGraph};

use crate::board::{Board, EdgeCoordinate, Index, PLACEMENT_SPIRAL, VertexCoordinate};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConfigError {
    InvalidPlayerCount,
}

/// An accepted setup placement made before the current choice.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PriorPlacement {
    pub seat: usize,
    pub vertex: VertexCoordinate,
    pub edge: EdgeCoordinate,
}

/// Errors and the two setup placements recorded for each seat, in seat order.
///
/// Each placement is the town vertex and the road edge chosen together.
/// A slot is [`None`] when that turn was not completed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Report {
    pub errors: Vec<Vec<String>>,
    pub placements: Vec<[Option<(VertexCoordinate, EdgeCoordinate)>; 2]>,
}

/// A setup player. [`Simulator::simulate`] calls [`Player::choose`] on each of that seat's turns.
pub trait Player {
    /// Chooses the town vertex and the road edge for this setup turn.
    ///
    /// `available` is the legal pairs, sorted by vertex then edge. `prior` contains
    /// accepted placements in chronological order. `errors` contains this seat's
    /// messages from previous invalid choices. `Err` is recorded like a rejected
    /// pair and counts toward `max_errors`.
    fn choose(
        &mut self,
        board: &Board,
        available: &[(VertexCoordinate, EdgeCoordinate)],
        prior: &[PriorPlacement],
        errors: &[String],
    ) -> Result<(VertexCoordinate, EdgeCoordinate), String>;
}

/// The setup snake draft.
///
/// Each player is indexed by its position in `players`. The first round calls
/// players from first to last. The second round calls them from last to first.
/// There must be 3 or 4 players. The board is fixed for the whole draft.
pub struct Simulator {
    board: Board,
    players: Vec<Box<dyn Player>>,
    graph: UnGraph<VertexCoordinate, EdgeCoordinate>,
    nodes: HashMap<VertexCoordinate, NodeIndex>,
    available_vertices: HashSet<VertexCoordinate>,
    available_edges: HashSet<EdgeCoordinate>,
    prior: Vec<PriorPlacement>,
    placements: Vec<[Option<(VertexCoordinate, EdgeCoordinate)>; 2]>,
}

impl Simulator {
    pub fn new(board: Board, players: Vec<Box<dyn Player>>) -> Result<Self, ConfigError> {
        let seat_count = players.len();
        if !(3..=4).contains(&seat_count) {
            return Err(ConfigError::InvalidPlayerCount);
        }

        let topology = board_topology();
        Ok(Self {
            board,
            players,
            graph: topology.graph,
            nodes: topology.nodes,
            available_vertices: topology.vertices,
            available_edges: topology.edges,
            prior: Vec::with_capacity(seat_count * 2),
            placements: vec![[None, None]; seat_count],
        })
    }

    /// Runs the setup snake draft.
    ///
    /// Each seat chooses a town and a connected road. An invalid choice is stored
    /// for that seat and the seat is asked again. When a seat's error count reaches
    /// `max_errors`, the draft stops and the report includes whatever was placed.
    pub fn simulate(&mut self, max_errors: usize) -> Report {
        let seat_count = self.players.len();
        let mut errors = vec![Vec::new(); seat_count];

        for seat in (0..seat_count).chain((0..seat_count).rev()) {
            loop {
                let available = self.available_pairs();
                let choice = {
                    let board = &self.board;
                    let player = &mut self.players[seat];
                    player.choose(board, &available, &self.prior, &errors[seat])
                };
                let (vertex, edge) = match choice {
                    Ok(pair) => pair,
                    Err(message) => {
                        errors[seat].push(message);
                        if errors[seat].len() >= max_errors {
                            return Report {
                                errors,
                                placements: self.placements.clone(),
                            };
                        }
                        continue;
                    }
                };
                if let Some(message) = self.rejection(vertex, edge) {
                    errors[seat].push(message);
                    if errors[seat].len() >= max_errors {
                        return Report {
                            errors,
                            placements: self.placements.clone(),
                        };
                    }
                } else {
                    self.apply(seat, vertex, edge);
                    break;
                }
            }
        }

        Report {
            errors,
            placements: self.placements.clone(),
        }
    }

    fn rejection(&self, vertex: VertexCoordinate, edge: EdgeCoordinate) -> Option<String> {
        if !self.nodes.contains_key(&vertex) {
            Some(format!("vertex {vertex:?} is not on the board"))
        } else if !self.available_vertices.contains(&vertex) {
            Some(format!("vertex {vertex:?} is not available"))
        } else if !self.edge_on_board(edge) {
            Some(format!("edge {edge:?} is not on the board"))
        } else if !self.available_edges.contains(&edge) {
            Some(format!("edge {edge:?} is not available"))
        } else if !self.edge_touches(vertex, edge) {
            Some(format!("edge {edge:?} is not connected to the vertex"))
        } else {
            None
        }
    }

    /// Legal town-and-road pairs, sorted by vertex then edge.
    fn available_pairs(&self) -> Vec<(VertexCoordinate, EdgeCoordinate)> {
        let mut pairs = Vec::new();
        for (&vertex, &node) in &self.nodes {
            if !self.available_vertices.contains(&vertex) {
                continue;
            }
            for edge_ref in self.graph.edges(node) {
                let edge = *edge_ref.weight();
                if self.available_edges.contains(&edge) {
                    pairs.push((vertex, edge));
                }
            }
        }
        pairs.sort_unstable();
        pairs
    }

    fn edge_on_board(&self, edge: EdgeCoordinate) -> bool {
        self.graph.edge_weights().any(|weight| *weight == edge)
    }

    fn edge_touches(&self, vertex: VertexCoordinate, edge: EdgeCoordinate) -> bool {
        let node = self.nodes[&vertex];
        self.graph
            .edges(node)
            .any(|candidate| *candidate.weight() == edge)
    }

    fn apply(&mut self, seat: usize, vertex: VertexCoordinate, edge: EdgeCoordinate) {
        let node = self.nodes[&vertex];
        let neighbors: Vec<VertexCoordinate> = self
            .graph
            .neighbors(node)
            .map(|neighbor| self.graph[neighbor])
            .collect();
        self.available_vertices.remove(&vertex);
        for neighbor in neighbors {
            self.available_vertices.remove(&neighbor);
        }
        self.available_edges.remove(&edge);
        self.prior.push(PriorPlacement { seat, vertex, edge });
        let open = self.placements[seat]
            .iter_mut()
            .find(|placement| placement.is_none())
            .expect("each seat places twice");
        *open = Some((vertex, edge));
    }
}

struct Topology {
    graph: UnGraph<VertexCoordinate, EdgeCoordinate>,
    nodes: HashMap<VertexCoordinate, NodeIndex>,
    vertices: HashSet<VertexCoordinate>,
    edges: HashSet<EdgeCoordinate>,
}

/// Vertices and edges of the fixed 19-hex island.
///
/// Edge `index` runs from vertex `index` to the next clockwise vertex, because
/// vertex `v` sits between edges `v` and `v - 1`.
fn board_topology() -> Topology {
    let mut graph = UnGraph::new_undirected();
    let mut nodes = HashMap::new();
    let mut edges = HashSet::new();

    for &(q, r) in &PLACEMENT_SPIRAL {
        for index in Index::ALL {
            let vertex = VertexCoordinate::new(q, r, index);
            nodes
                .entry(vertex)
                .or_insert_with(|| graph.add_node(vertex));
        }
        for index in Index::ALL {
            let edge = EdgeCoordinate::new(q, r, index);
            if edges.insert(edge) {
                let start = VertexCoordinate::new(q, r, index);
                let end = VertexCoordinate::new(q, r, index.clockwise());
                graph.add_edge(nodes[&start], nodes[&end], edge);
            }
        }
    }

    Topology {
        vertices: nodes.keys().copied().collect(),
        graph,
        nodes,
        edges,
    }
}

/// Neighbors of every intersection, keyed by canonical [`VertexCoordinate`].
pub fn vertex_neighbors() -> HashMap<VertexCoordinate, Vec<VertexCoordinate>> {
    let Topology { graph, .. } = board_topology();
    graph
        .node_indices()
        .map(|node| {
            let mut neighbors: Vec<_> = graph
                .neighbors(node)
                .map(|neighbor| graph[neighbor])
                .collect();
            neighbors.sort_unstable();
            (graph[node], neighbors)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;
    use std::collections::HashSet;
    use std::rc::Rc;

    use petgraph::visit::EdgeRef;

    use super::*;
    use crate::Index;

    struct Idle;

    impl Player for Idle {
        fn choose(
            &mut self,
            _board: &Board,
            _available: &[(VertexCoordinate, EdgeCoordinate)],
            _prior: &[PriorPlacement],
            _errors: &[String],
        ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
            unreachable!("player count is rejected before choose");
        }
    }

    struct Scripted {
        id: usize,
        calls: Rc<RefCell<Vec<usize>>>,
        choices: Vec<(VertexCoordinate, EdgeCoordinate)>,
        cursor: usize,
        seen_errors: Rc<RefCell<Vec<Vec<String>>>>,
        seen_prior: Rc<RefCell<Vec<Vec<PriorPlacement>>>>,
    }

    impl Scripted {
        fn new(
            id: usize,
            calls: Rc<RefCell<Vec<usize>>>,
            choices: Vec<(VertexCoordinate, EdgeCoordinate)>,
        ) -> Self {
            Self {
                id,
                calls,
                choices,
                cursor: 0,
                seen_errors: Rc::new(RefCell::new(Vec::new())),
                seen_prior: Rc::new(RefCell::new(Vec::new())),
            }
        }

        fn watching(mut self, seen_errors: Rc<RefCell<Vec<Vec<String>>>>) -> Self {
            self.seen_errors = seen_errors;
            self
        }

        fn watching_prior(mut self, seen_prior: Rc<RefCell<Vec<Vec<PriorPlacement>>>>) -> Self {
            self.seen_prior = seen_prior;
            self
        }
    }

    impl Player for Scripted {
        fn choose(
            &mut self,
            board: &Board,
            _available: &[(VertexCoordinate, EdgeCoordinate)],
            prior: &[PriorPlacement],
            errors: &[String],
        ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
            assert_eq!(board.tiles.len(), 18);
            self.calls.borrow_mut().push(self.id);
            self.seen_errors.borrow_mut().push(errors.to_vec());
            self.seen_prior.borrow_mut().push(prior.to_vec());
            let choice = self.choices[self.cursor];
            self.cursor += 1;
            Ok(choice)
        }
    }

    struct OffBoard {
        seen_errors: Rc<RefCell<Vec<Vec<String>>>>,
    }

    impl Player for OffBoard {
        fn choose(
            &mut self,
            _board: &Board,
            _available: &[(VertexCoordinate, EdgeCoordinate)],
            _prior: &[PriorPlacement],
            errors: &[String],
        ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
            self.seen_errors.borrow_mut().push(errors.to_vec());
            Ok((
                VertexCoordinate::new(5, 5, Index::Zero),
                EdgeCoordinate::new(9, 9, Index::Three),
            ))
        }
    }

    struct Counting {
        calls: Rc<RefCell<u8>>,
    }

    impl Player for Counting {
        fn choose(
            &mut self,
            _board: &Board,
            _available: &[(VertexCoordinate, EdgeCoordinate)],
            _prior: &[PriorPlacement],
            _errors: &[String],
        ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
            *self.calls.borrow_mut() += 1;
            Ok((
                VertexCoordinate::new(0, 0, Index::Zero),
                EdgeCoordinate::new(0, 0, Index::Zero),
            ))
        }
    }

    fn spaced_placements(count: usize) -> Vec<(VertexCoordinate, EdgeCoordinate)> {
        let Topology { graph, .. } = board_topology();
        let mut blocked = HashSet::new();
        let mut used_edges = HashSet::new();
        let mut placements = Vec::new();
        let mut nodes: Vec<_> = graph.node_indices().collect();
        nodes.sort_by_key(|node| graph[*node]);

        for node in nodes {
            let vertex = graph[node];
            if blocked.contains(&vertex) {
                continue;
            }
            let edge = graph
                .edges(node)
                .map(|edge_ref| *edge_ref.weight())
                .find(|edge| !used_edges.contains(edge));
            let Some(edge) = edge else {
                continue;
            };
            placements.push((vertex, edge));
            blocked.insert(vertex);
            for neighbor in graph.neighbors(node) {
                blocked.insert(graph[neighbor]);
            }
            used_edges.insert(edge);
            if placements.len() == count {
                break;
            }
        }

        assert_eq!(placements.len(), count);
        placements
    }

    fn seat_choices(
        spaced: &[(VertexCoordinate, EdgeCoordinate)],
        seat: usize,
    ) -> Vec<(VertexCoordinate, EdgeCoordinate)> {
        let last = spaced.len() - 1;
        vec![spaced[seat], spaced[last - seat]]
    }

    fn neighbor_of(vertex: VertexCoordinate) -> VertexCoordinate {
        let Topology { graph, nodes, .. } = board_topology();
        let neighbor = graph
            .neighbors(nodes[&vertex])
            .next()
            .expect("every board vertex has a neighbor");
        graph[neighbor]
    }

    fn edge_not_touching(
        vertex: VertexCoordinate,
        reserved: &HashSet<EdgeCoordinate>,
    ) -> EdgeCoordinate {
        let Topology { graph, nodes, .. } = board_topology();
        let node = nodes[&vertex];
        let incident: HashSet<_> = graph.edges(node).map(|edge| *edge.weight()).collect();
        graph
            .edge_weights()
            .copied()
            .find(|edge| !incident.contains(edge) && !reserved.contains(edge))
            .expect("some edge is not incident to the vertex")
    }

    fn assert_snake_order(seats: usize, expected_calls: &[usize]) {
        let spaced = spaced_placements(seats * 2);
        let calls = Rc::new(RefCell::new(Vec::new()));
        let players: Vec<Box<dyn Player>> = (0..seats)
            .map(|seat| {
                Box::new(Scripted::new(
                    seat,
                    Rc::clone(&calls),
                    seat_choices(&spaced, seat),
                )) as Box<dyn Player>
            })
            .collect();
        let board = Board::from_seed(seats as u64);
        let mut simulator = Simulator::new(board.clone(), players).unwrap();

        let report = simulator.simulate(1);

        assert_eq!(*calls.borrow(), expected_calls);
        assert_eq!(simulator.board, board);
        assert_eq!(report.placements.len(), seats);
        for seat in 0..seats {
            let choices = seat_choices(&spaced, seat);
            assert_eq!(
                report.placements[seat],
                [Some(choices[0]), Some(choices[1])]
            );
        }
        assert!(
            report
                .errors
                .iter()
                .all(|seat_errors| seat_errors.is_empty())
        );
    }

    #[test]
    fn board_graph_has_the_standard_vertex_and_edge_counts() {
        let Topology {
            graph,
            nodes,
            vertices,
            edges,
        } = board_topology();
        assert_eq!(graph.node_count(), 54);
        assert_eq!(graph.edge_count(), 72);
        assert_eq!(vertices.len(), 54);
        assert_eq!(edges.len(), 72);

        let start = VertexCoordinate::new(0, 0, Index::Zero);
        let end = VertexCoordinate::new(0, 0, Index::One);
        let edge = EdgeCoordinate::new(0, 0, Index::Zero);
        assert!(graph.edges(nodes[&start]).any(|candidate| {
            *candidate.weight() == edge
                && (graph[candidate.source()] == end || graph[candidate.target()] == end)
        }));
    }

    #[test]
    fn vertex_neighbors_are_symmetric_and_coastal_or_interior() {
        let neighbors = vertex_neighbors();
        assert_eq!(neighbors.len(), 54);
        for (vertex, adjacent) in &neighbors {
            assert!((2..=3).contains(&adjacent.len()), "{vertex:?}");
            for neighbor in adjacent {
                assert!(neighbors[neighbor].contains(vertex));
            }
        }
    }

    #[test]
    fn rejects_player_counts_other_than_three_or_four() {
        for count in [0, 1, 2, 5] {
            let players: Vec<Box<dyn Player>> = (0..count)
                .map(|_| Box::new(Idle) as Box<dyn Player>)
                .collect();
            assert!(matches!(
                Simulator::new(Board::from_seed(0), players),
                Err(ConfigError::InvalidPlayerCount)
            ));
        }
    }

    #[test]
    fn seat_order_follows_the_players_then_reverses() {
        assert_snake_order(3, &[0, 1, 2, 2, 1, 0]);
    }

    #[test]
    fn four_players_reverse_on_the_second_round() {
        assert_snake_order(4, &[0, 1, 2, 3, 3, 2, 1, 0]);
    }

    #[test]
    fn prior_placements_are_chronological_and_include_seats() {
        let seats = 3;
        let spaced = spaced_placements(seats * 2);
        let calls = Rc::new(RefCell::new(Vec::new()));
        let seen = Rc::new(RefCell::new(Vec::new()));
        let players: Vec<Box<dyn Player>> = (0..seats)
            .map(|seat| {
                Box::new(
                    Scripted::new(seat, Rc::clone(&calls), seat_choices(&spaced, seat))
                        .watching_prior(Rc::clone(&seen)),
                ) as Box<dyn Player>
            })
            .collect();
        let mut simulator = Simulator::new(Board::from_seed(0), players).unwrap();

        simulator.simulate(1);

        let order = [0, 1, 2, 2, 1, 0];
        let choices = [
            spaced[0], spaced[1], spaced[2], spaced[3], spaced[4], spaced[5],
        ];
        for (offset, prior) in seen.borrow().iter().enumerate() {
            assert_eq!(prior.len(), offset);
            for index in 0..offset {
                assert_eq!(
                    prior[index],
                    PriorPlacement {
                        seat: order[index],
                        vertex: choices[index].0,
                        edge: choices[index].1,
                    }
                );
            }
        }
    }

    #[test]
    fn neighbor_of_a_town_is_rejected_then_a_legal_vertex_is_placed() {
        let seats = 3;
        let spaced = spaced_placements(seats * 2);
        let neighbor = neighbor_of(spaced[0].0);
        let message = format!("vertex {neighbor:?} is not available");
        let calls = Rc::new(RefCell::new(Vec::new()));
        let seen = Rc::new(RefCell::new(Vec::new()));
        let first = Scripted::new(0, Rc::clone(&calls), seat_choices(&spaced, 0));
        let second = Scripted::new(
            1,
            Rc::clone(&calls),
            vec![(neighbor, spaced[1].1), spaced[1], spaced[4]],
        )
        .watching(Rc::clone(&seen));
        let third = Scripted::new(2, Rc::clone(&calls), seat_choices(&spaced, 2));
        let players: Vec<Box<dyn Player>> =
            vec![Box::new(first), Box::new(second), Box::new(third)];
        let mut simulator = Simulator::new(Board::from_seed(1), players).unwrap();

        let report = simulator.simulate(2);

        assert_eq!(seen.borrow()[1], vec![message.clone()]);
        assert_eq!(report.errors[1], vec![message]);
        assert_eq!(report.placements[1], [Some(spaced[1]), Some(spaced[4])]);
        assert!(
            report
                .placements
                .iter()
                .flatten()
                .flatten()
                .all(|(vertex, _)| *vertex != neighbor)
        );
    }

    #[test]
    fn edge_that_does_not_touch_the_vertex_is_rejected_and_not_consumed() {
        let seats = 3;
        let spaced = spaced_placements(seats * 2);
        let reserved: HashSet<_> = spaced.iter().map(|(_, edge)| *edge).collect();
        let bad_edge = edge_not_touching(spaced[0].0, &reserved);
        let message = format!("edge {bad_edge:?} is not connected to the vertex");
        let calls = Rc::new(RefCell::new(Vec::new()));
        let seen = Rc::new(RefCell::new(Vec::new()));
        let first = Scripted::new(
            0,
            Rc::clone(&calls),
            vec![(spaced[0].0, bad_edge), spaced[0], spaced[5]],
        )
        .watching(Rc::clone(&seen));
        let second = Scripted::new(1, Rc::clone(&calls), seat_choices(&spaced, 1));
        let third = Scripted::new(2, Rc::clone(&calls), seat_choices(&spaced, 2));
        let players: Vec<Box<dyn Player>> =
            vec![Box::new(first), Box::new(second), Box::new(third)];
        let mut simulator = Simulator::new(Board::from_seed(1), players).unwrap();

        let report = simulator.simulate(2);

        assert_eq!(seen.borrow()[1], vec![message.clone()]);
        assert_eq!(report.errors[0], vec![message]);
        assert!(simulator.available_edges.contains(&bad_edge));
        assert!(!simulator.available_edges.contains(&spaced[0].1));
        assert_eq!(simulator.available_edges.len(), 72 - seats * 2);
        assert_eq!(report.placements[0], [Some(spaced[0]), Some(spaced[5])]);
        assert!(
            report
                .placements
                .iter()
                .flatten()
                .flatten()
                .all(|(_, edge)| *edge != bad_edge)
        );
    }

    #[test]
    fn edge_already_used_is_rejected_and_not_consumed_again() {
        let seats = 3;
        let spaced = spaced_placements(seats * 2);
        let used_edge = spaced[0].1;
        let message = format!("edge {used_edge:?} is not available");
        let calls = Rc::new(RefCell::new(Vec::new()));
        let seen = Rc::new(RefCell::new(Vec::new()));
        let first = Scripted::new(0, Rc::clone(&calls), seat_choices(&spaced, 0));
        let second = Scripted::new(
            1,
            Rc::clone(&calls),
            vec![(spaced[1].0, used_edge), spaced[1], spaced[4]],
        )
        .watching(Rc::clone(&seen));
        let third = Scripted::new(2, Rc::clone(&calls), seat_choices(&spaced, 2));
        let players: Vec<Box<dyn Player>> =
            vec![Box::new(first), Box::new(second), Box::new(third)];
        let mut simulator = Simulator::new(Board::from_seed(1), players).unwrap();

        let report = simulator.simulate(2);

        assert_eq!(seen.borrow()[1], vec![message.clone()]);
        assert_eq!(report.errors[1], vec![message]);
        assert!(!simulator.available_edges.contains(&used_edge));
        assert_eq!(simulator.available_edges.len(), 72 - seats * 2);
        assert_eq!(report.placements[1], [Some(spaced[1]), Some(spaced[4])]);
        assert_eq!(
            report
                .placements
                .iter()
                .flatten()
                .flatten()
                .filter(|(_, edge)| *edge == used_edge)
                .count(),
            1
        );
    }

    #[test]
    fn max_errors_stops_the_draft_before_later_seats_play() {
        let vertex = VertexCoordinate::new(5, 5, Index::Zero);
        let message = format!("vertex {vertex:?} is not on the board");
        let seen = Rc::new(RefCell::new(Vec::new()));
        let later = Rc::new(RefCell::new(0u8));
        let first = OffBoard {
            seen_errors: Rc::clone(&seen),
        };
        let second = Counting {
            calls: Rc::clone(&later),
        };
        let third = Counting {
            calls: Rc::clone(&later),
        };
        let players: Vec<Box<dyn Player>> =
            vec![Box::new(first), Box::new(second), Box::new(third)];
        let mut simulator = Simulator::new(Board::from_seed(0), players).unwrap();

        let report = simulator.simulate(2);

        assert_eq!(seen.borrow().len(), 2);
        assert_eq!(seen.borrow()[0], Vec::<String>::new());
        assert_eq!(seen.borrow()[1], vec![message.clone()]);
        assert_eq!(report.errors[0], vec![message.clone(), message]);
        assert!(report.errors[1].is_empty());
        assert!(report.errors[2].is_empty());
        assert_eq!(report.placements, vec![[None, None]; 3]);
        assert_eq!(*later.borrow(), 0);
        assert_eq!(simulator.available_vertices.len(), 54);
        assert_eq!(simulator.available_edges.len(), 72);
    }

    struct FirstPairs {
        seen: Rc<RefCell<Vec<(VertexCoordinate, EdgeCoordinate)>>>,
    }

    impl Player for FirstPairs {
        fn choose(
            &mut self,
            _board: &Board,
            available: &[(VertexCoordinate, EdgeCoordinate)],
            _prior: &[PriorPlacement],
            _errors: &[String],
        ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
            self.seen.borrow_mut().extend(available.iter().copied());
            Err("stop".to_string())
        }
    }

    struct Rejects;

    impl Player for Rejects {
        fn choose(
            &mut self,
            _board: &Board,
            _available: &[(VertexCoordinate, EdgeCoordinate)],
            _prior: &[PriorPlacement],
            _errors: &[String],
        ) -> Result<(VertexCoordinate, EdgeCoordinate), String> {
            Err("unreadable choice".to_string())
        }
    }

    #[test]
    fn first_choice_receives_every_legal_pair_sorted() {
        let seen = Rc::new(RefCell::new(Vec::new()));
        let players: Vec<Box<dyn Player>> = vec![
            Box::new(FirstPairs {
                seen: Rc::clone(&seen),
            }),
            Box::new(Idle),
            Box::new(Idle),
        ];
        let mut simulator = Simulator::new(Board::from_seed(0), players).unwrap();
        let _report = simulator.simulate(1);

        let pairs = seen.borrow();
        assert_eq!(pairs.len(), 144);
        assert!(pairs.is_sorted());
        assert!(pairs.iter().all(|(vertex, edge)| {
            simulator.edge_touches(*vertex, *edge) && simulator.edge_on_board(*edge)
        }));
    }

    #[test]
    fn player_error_counts_toward_max_errors() {
        let players: Vec<Box<dyn Player>> = vec![Box::new(Rejects), Box::new(Idle), Box::new(Idle)];
        let mut simulator = Simulator::new(Board::from_seed(0), players).unwrap();

        let report = simulator.simulate(1);

        assert_eq!(report.errors[0], vec!["unreadable choice".to_string()]);
        assert!(report.errors[1].is_empty());
        assert!(report.errors[2].is_empty());
        assert_eq!(report.placements, vec![[None, None]; 3]);
    }
}
