mod diversity;
mod generic_port;
mod production;
mod resource_combos;
mod specific_port;

use crate::metric::Metric;
use diversity::Diversity;
use generic_port::GenericPort;
use production::Production;
use resource_combos::ResourceCombos;
use specific_port::SpecificPort;

/// Heuristics from `docs/heuristics.md`, in document order.
pub fn metrics() -> Vec<Box<dyn Metric>> {
    vec![
        Box::new(ResourceCombos),
        Box::new(SpecificPort),
        Box::new(GenericPort),
        Box::new(Production),
        Box::new(Diversity),
    ]
}
