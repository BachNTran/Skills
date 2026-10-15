// Package extra holds small Go helpers.
package extra

import (
	"fmt"
	str "strings"
)

// Greeter says hello to a name.
type Greeter struct {
	Name  string
	count int
}

// Hello says hi.
func Hello() string {
	return fmt.Sprintf("hi %s", "}")
}

// Greet greets g.Name.
func (g *Greeter) Greet() string {
	g.count++
	raw := `}{ backtick`
	return str.ToUpper(Hello()) + g.Name + raw
}

func helper() int { return len("x") }
