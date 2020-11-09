#include <iostream>

#include "type_int.h"

using namespace spec;

int main() {
    RandInt<int> ri;
    ri.data(2);
    ri.validate();

    TypeInt<uint8_t> ti;
    cout << ti.size().value() << endl;

    return 0;
}