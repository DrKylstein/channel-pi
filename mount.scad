include <../libraries-OpenSCAD/wedge.scad>;

$fs = 1;
mm = 1;
tolerance = 0.4*mm;
screw_d = 2.5*mm + tolerance;
screw_space = [58,23]*mm;
screw_inset = 3.5*mm;

jack_d = 8*mm + tolerance;
button_d = 9.25*mm + tolerance;

wall = 2*mm;
space = 20*mm;
jack_space = 5*mm;

difference() {
    union() {
        difference() {
            cube([65*mm,wall,35*mm]);
            translate([jack_d/2 + jack_space,-1,28*mm]) {
                for(i = [0,1,2]) {
                    translate([1,0,0]*i*(jack_d+jack_space)) {
                        rotate([-90,0,0]) cylinder(d=jack_d,h=wall+2);
                    }
                }
                translate([45*mm,0,0]) {
                        rotate([-90,0,0]) cylinder(d=button_d,h=wall+2);
                    }
            }
        }
        difference() {
            cube([65*mm,30*mm+space,wall]);
            translate([1,1,0]*screw_inset + [0,1,0]*space + [0,0,-1]) {
                for(x = [0,screw_space[0]], y = [0,screw_space[1]]) {
                    translate([x,y,0]) {
                        cylinder(d = screw_d, h = wall+2);
                    }
                }
            }
        }
        translate([0,20,0]*mm) {
            for(x = [0,65*mm-wall]) {
                translate([x,0,0]) rotate([0,0,-90]) {
                    wedge([20,wall,30]);
                }
            }
        }
    }
    translate([7,10,-1]) cube([50,60,10]);
}