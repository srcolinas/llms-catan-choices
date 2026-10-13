use std::path::{Path, PathBuf};
use std::process::ExitCode;

fn usage() -> ! {
    eprintln!(
        "Usage: catan-placement-evaluate [INPUT] [-o|--output OUTPUT]\n\
         Defaults: INPUT=data/choices.jsonl OUTPUT=data/evaluation.jsonl"
    );
    std::process::exit(2);
}

fn parse_args() -> (PathBuf, PathBuf) {
    let mut input = PathBuf::from("data/choices.jsonl");
    let mut output = PathBuf::from("data/evaluation.jsonl");
    let mut args = std::env::args().skip(1);
    let mut saw_positional = false;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "-o" | "--output" => {
                let Some(path) = args.next() else {
                    usage();
                };
                output = PathBuf::from(path);
            }
            "-h" | "--help" => usage(),
            flag if flag.starts_with('-') => {
                eprintln!("unknown flag: {flag}");
                usage();
            }
            path if !saw_positional => {
                input = PathBuf::from(path);
                saw_positional = true;
            }
            _ => usage(),
        }
    }

    (input, output)
}

fn main() -> ExitCode {
    let (input, output) = parse_args();
    match catan_placement_evaluate::run_and_write(Path::new(&input), Path::new(&output)) {
        Ok((_rows, reports)) => {
            for report in reports {
                let total = report.passed.iter().map(|seats| seats.len()).sum::<usize>();
                let passed = report
                    .passed
                    .iter()
                    .flat_map(|seats| seats.iter())
                    .filter(|ok| **ok)
                    .count();
                println!("{} {}/{}", report.name, passed, total);
            }
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("{err}");
            ExitCode::FAILURE
        }
    }
}
