//! Small Rust helpers for the poly fixture.

use std::fmt::{self, Display};

/* outer /* nested */ still a comment } */

/// Adds.
pub fn add<'a>(x: &'a str) -> usize {
    let raw = r#"}"#;
    x.len() + raw.len() + helper('}')
}

fn helper(c: char) -> usize {
    if c == '}' { 1 } else { 0 }
}

/// A named thing.
pub struct Thing {
    pub name: String,
}

/// Something that can be shown.
pub trait Show {
    /// Render as text.
    fn show(&self) -> String;
}

impl Show for Thing {
    fn show(&self) -> String {
        format!("{}", self.name)
    }
}

impl Display for Thing {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.name)
    }
}
