# R# - RSX-R
A compiled statically typed multi paradigm general purpose programming language designed for cross platform applications.

# RSX Logo
![R# Logo](rsxr/logo.png)

# RSX Icon
![R# Icon](rsxr/icon.png)

# Requirements
- Python 3.10 or higher

# Getting Started
## How to install
### Windows (Installs the RSX-R python library)
```
.\install.bat
```

### Linux (Installs the RSX-R python library)
```
./install.sh
```

# Examples
## Hello, World!
```c++
include "rsxrio" : *;

// using namespace std;

int main() {
    std::rout("Hello, World!", std::endl());
    return 0;
}```

## Factorial and Fibonacci
```c++
include "rsxrio" : *;

int factorial(int n) {
    if (n == 1) return n;
    return factorial(n - 1) * n;
}

int fibonacci(int n) {
    if (n <= 1) return n;
    return fibonacci(n - 1) + fibonacci(n - 2);
}

int main() {
    int n;
    n = 5; printf("factorial(%d) = %d\n", n, factorial(n));
    n = 8; printf("fibonacci(%d) = %d\n", n, fibonacci(n));
    return 0;
}```

# Libraries
- rsxrio
- rsxrmath
- rsxrglfw
- rsxrgl
- rsxr-rvr