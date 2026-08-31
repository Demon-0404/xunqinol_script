// Find and call jlapp_jumpUrl via Java bridge
// This JNI function is at ARM offset 0x1375d0, registered via RegisterNatives
// We need to find the Java class that registered it, then call it

Java.perform(function() {
    send({t: 'log', msg: 'Java bridge active, searching for jumpUrl native method...'});

    // First try: common Cocos2d-x activity class names
    var candidateClasses = [
        'com.xqj.games.MainActivity',
        'com.xqj.games.AppActivity',
        'org.cocos2dx.cpp.AppActivity',
        'org.cocos2dx.lib.Cocos2dxActivity',
        'org.cocos2dx.javascript.AppActivity',
        'com.xqj.games.Cocos2dxActivity',
    ];

    var foundClass = null;
    var foundMethod = null;

    // Try each candidate class
    for (var ci = 0; ci < candidateClasses.length; ci++) {
        try {
            var clazz = Java.use(candidateClasses[ci]);
            var methods = clazz.class.getDeclaredMethods();
            for (var mi = 0; mi < methods.length; mi++) {
                var m = methods[mi];
                var name = m.getName();
                if (name.indexOf('jumpUrl') !== -1 || name.indexOf('jump') !== -1) {
                    send({t: 'log', msg: 'FOUND in ' + candidateClasses[ci] + ': ' + name + ' ' + m.toString()});
                    if (name === 'jumpUrl' || name === 'jlapp_jumpUrl') {
                        foundClass = candidateClasses[ci];
                        foundMethod = name;
                    }
                }
            }
        } catch(e) {
            // Class not found or not accessible
        }
    }

    // Second try: enumerate all loaded classes (filtered to likely packages)
    if (!foundClass) {
        send({t: 'log', msg: 'Candidate classes exhausted, enumerating loaded classes...'});
        Java.enumerateLoadedClasses({
            onMatch: function(className) {
                // Only check classes in relevant packages
                if (className.indexOf('xqj') === -1 &&
                    className.indexOf('cocos') === -1 &&
                    className.indexOf('proj') === -1 &&
                    className.indexOf('game') === -1) {
                    return;
                }
                try {
                    var clazz2 = Java.use(className);
                    var methods2 = clazz2.class.getDeclaredMethods();
                    for (var mi2 = 0; mi2 < methods2.length; mi2++) {
                        var m2 = methods2[mi2];
                        var n2 = m2.getName();
                        if (n2.indexOf('jumpUrl') !== -1) {
                            send({t: 'log', msg: 'FOUND jumpUrl in: ' + className + '.' + n2});
                            foundClass = className;
                            foundMethod = n2;
                        }
                    }
                } catch(e) {}
            },
            onComplete: function() {
                send({t: 'log', msg: 'Enumeration complete. foundClass=' + foundClass + ' foundMethod=' + foundMethod});

                if (foundClass && foundMethod) {
                    tryCallMethod(foundClass, foundMethod);
                } else {
                    // Last resort: try to call via JNI directly using the known ARM address
                    send({t: 'log', msg: 'No Java class found. Trying alternative approaches...'});
                    tryAlternativeApproaches();
                }
            }
        });
    } else {
        tryCallMethod(foundClass, foundMethod);
    }

    function tryCallMethod(className, methodName) {
        send({t: 'log', msg: '=== Trying to call ' + className + '.' + methodName + ' ==='});

        try {
            var targetClass = Java.use(className);

            // Check if it's a static method or instance method
            var allMethods = targetClass.class.getDeclaredMethods();
            var isStatic = false;
            var paramTypes = [];
            for (var ai = 0; ai < allMethods.length; ai++) {
                if (allMethods[ai].getName() === methodName) {
                    isStatic = java.lang.reflect.Modifier.isStatic(allMethods[ai].getModifiers());
                    var pts = allMethods[ai].getParameterTypes();
                    for (var pi = 0; pi < pts.length; pi++) {
                        paramTypes.push(pts[pi].getName());
                    }
                    send({t: 'log', msg: 'Method details: static=' + isStatic + ' params=' + JSON.stringify(paramTypes)});
                    break;
                }
            }

            if (isStatic) {
                // Try calling with a URL string
                send({t: 'log', msg: 'Calling static ' + methodName + '("test://map/1")...'});
                var result = targetClass[methodName]('test://map/1');
                send({t: 'log', msg: 'Result: ' + result});
            } else {
                // Need an instance - try to get the current activity
                send({t: 'log', msg: 'Instance method — need to get activity instance first'});

                // Try via Android context
                try {
                    var ActivityThread = Java.use('android.app.ActivityThread');
                    var currentActivityThread = ActivityThread.currentActivityThread();
                    var mActivities = currentActivityThread.mActivities.value;
                    send({t: 'log', msg: 'Got ActivityThread, mActivities type: ' + typeof mActivities});

                    // Iterate to find our activity
                    var iter = mActivities.entrySet().iterator();
                    while (iter.hasNext()) {
                        var entry = iter.next();
                        var activity = entry.getValue().get();
                        var activityClassName = activity.getClass().getName();
                        send({t: 'log', msg: '  Activity: ' + activityClassName});
                        if (activityClassName === className) {
                            send({t: 'log', msg: '  Calling ' + methodName + ' on this instance...'});
                            var result2 = activity[methodName]('test://map/1');
                            send({t: 'log', msg: '  Result: ' + result2});
                            break;
                        }
                    }
                } catch(e2) {
                    send({t: 'err', msg: 'ActivityThread approach failed: ' + e2});
                }
            }
        } catch(e3) {
            send({t: 'err', msg: 'Error calling method: ' + e3});
        }
    }

    function tryAlternativeApproaches() {
        // Try to find the native method through System.loadLibrary reflection
        send({t: 'log', msg: 'Trying to find registered native methods...'});

        // Approach: dump all classes with "native" methods containing "Url" or "jump"
        Java.enumerateLoadedClasses({
            onMatch: function(className) {
                try {
                    var clazz3 = Java.use(className);
                    var methods3 = clazz3.class.getDeclaredMethods();
                    var hasNative = false;
                    for (var mi3 = 0; mi3 < methods3.length; mi3++) {
                        if (java.lang.reflect.Modifier.isNative(methods3[mi3].getModifiers())) {
                            var n3 = methods3[mi3].getName();
                            if (n3.indexOf('Url') !== -1 || n3.indexOf('jump') !== -1 || n3.indexOf('Jump') !== -1) {
                                send({t: 'log', msg: 'NATIVE: ' + className + '.' + n3 + ' ' + methods3[mi3].toString()});
                                foundClass = className;
                                foundMethod = n3;
                            }
                            hasNative = true;
                        }
                    }
                    if (hasNative && (className.indexOf('xqj') !== -1 || className.indexOf('proj') !== -1)) {
                        // Log all native methods in xqj/proj classes
                        for (var mi4 = 0; mi4 < methods3.length; mi4++) {
                            if (java.lang.reflect.Modifier.isNative(methods3[mi4].getModifiers())) {
                                send({t: 'log', msg: '  All native: ' + className + '.' + methods3[mi4].getName()});
                            }
                        }
                    }
                } catch(e4) {}
            },
            onComplete: function() {
                if (foundClass && foundMethod) {
                    tryCallMethod(foundClass, foundMethod);
                } else {
                    send({t: 'log', msg: 'No native jumpUrl found in any Java class.'});
                    send({t: 'log', msg: 'The function may be called from C++ only, not exposed to Java.'});
                    send({t: 'log', msg: 'jumpUrl ARM address: 0xc1ab5d0 (offset 0x1375d0 in libtestcpp.so)'});
                    send({t: 'log', msg: 'g_jumpUrlCall global at 0xc4d8a18, value=0xc4ba1e8'});
                }
                send({t: 'ready', msg: 'Java bridge exploration complete'});
            }
        });
    }
});
