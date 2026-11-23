from panda3d.core import *
from panda3d.physics import *
def run(fps, mode, secs=40, acc=16.0, mass=1.0):
    pm = PhysicsManager(); pm.attachLinearIntegrator(LinearEulerIntegrator())
    root = NodePath('r')
    fn = ForceNode('v'); root.attachNewNode(fn)
    visc = LinearFrictionForce(0.0, 1.0, 0); visc.setCoef(0.5); visc.setAmplitude(2); fn.addForce(visc); pm.addLinearForce(visc)
    fn2 = ForceNode('c'); root.attachNewNode(fn2)
    cf = LinearControlForce(); cf.setAmplitude(5); fn2.addForce(cf); pm.addLinearForce(cf)
    an = ActorNode('ship'); np = root.attachNewNode(an); pm.attachPhysicalNode(an)
    po = an.getPhysicsObject(); po.setMass(mass); cf.setPhysicsObject(po)
    dt = 1.0/fps; t = 0.0; sdt = 0.0; out = {}
    while t < secs:
        sdt += dt
        b = 0.0
        if sdt > 5.0: b = (sdt - 5.0) / 10.0 / 2.0
        if mode == 'old':
            b = b*4.0 + 1.0
            f = min(acc*b*dt, acc)
        else:
            b = min(4.0, b*4.0) + 1.0
            f = min(acc*b, acc)
        cf.setVector(Vec3(0, f, 0))
        pm.doPhysics(dt)
        t += dt
        for mark in (5, 10, 20, 40):
            if abs(t-mark) < dt/2: out[mark] = round(np.getY(), 0), round(po.getVelocity().length(), 1)
    return out
print('massDependent', LinearControlForce().getMassDependent(), 'ship mass stat is 20; physobj default mass', PhysicsObject().getMass())
for m in ('old','new'):
    for fps in (120, 60, 30, 13):
        print(m, fps, 'fps  t:(dist,vel)', run(fps, m))

