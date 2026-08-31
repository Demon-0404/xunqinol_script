// List all modules, look for game-specific ones
var allMods = Process.enumerateModules();
var gameLibs = [];
var unknownLibs = [];

var knownSystem = ['linker', 'libc', 'libm', 'libdl', 'libstdc++', 'liblog',
    'libcutils', 'libutils', 'libbinder', 'libui', 'libgui', 'libEGL', 'libGLES',
    'libandroid', 'libhwui', 'libmedia', 'libstagefright', 'libaudioclient',
    'libicu', 'libsqlite', 'libcrypto', 'libssl', 'libjpeg', 'libpng',
    'libz', 'libexpat', 'libft2', 'libharfbuzz', 'libpdfium', 'libminikin',
    'libart', 'libnative', 'libbase', 'libc++', 'libvulkan', 'libhardware',
    'libhidl', 'libvndk', 'libbpf', 'libnetd', 'libdebuggerd', 'libbacktrace',
    'libunwind', 'libzip', 'liblz4', 'liblzma', 'libpackagelist',
    'libtombstoned', 'libcgrouprc', 'libdexfile', 'libprofile', 'libsigchain',
    'libxml2', 'libtinyxml2', 'libprotobuf', 'libcodec2', 'libsfplugin',
    'libRScpp', 'libspeex', 'libfmq', 'libgralloc', 'libsync', 'libincfs',
    'libion', 'libdmabuf', 'libpcre2', 'libselinux', 'libprocinfo',
    'libmeminfo', 'libmemtrack', 'libmemunreachable', 'libdrm', 'libaaudio',
    'libamidi', 'libOpenMAX', 'libOpenSLES', 'libwilhelm', 'libnblog',
    'libhidlmemory', 'libbufferhub', 'libpdx', 'libinput', 'libsensor',
    'libcamera', 'libusbhost', 'libvibrator', 'libshmem', 'libsurfaceflinger',
    'libtimeinstate', 'libaudiomanager', 'libdatasource', 'libdng_sdk',
    'libpiex', 'libheif', 'libdataloader', 'libimg_utils', 'libprocessgroup',
    'libadbconnection', 'libstatssocket', 'libperfetto', 'libandroidio',
    'libopenjdk', 'libandroidemu'];

allMods.forEach(function(m) {
    var name = m.name;
    var isSystem = false;
    for (var i = 0; i < knownSystem.length; i++) {
        if (name.toLowerCase().indexOf(knownSystem[i].toLowerCase()) !== -1) {
            isSystem = true;
            break;
        }
    }
    if (!isSystem && !name.startsWith('boot') && !name.endsWith('.odex') &&
        !name.endsWith('.oat') && !name.startsWith('framework') &&
        !name.startsWith('audio') && !name.startsWith('android.') &&
        !name.startsWith('mediacodec') && !name.startsWith('gralloc') &&
        !name.startsWith('server_') && !name.startsWith('effect-') &&
        !name.startsWith('spatializer') && !name.startsWith('av-') &&
        !name.startsWith('capture_') && !name.startsWith('audiopolicy') &&
        !name.startsWith('mediametrics')) {
        unknownLibs.push(m.name + ' @ ' + m.base + ' size=' + m.size);
    }
});

send({t: 'unknown_libs', count: unknownLibs.length, libs: unknownLibs});

// Also list ALL modules sorted
var sorted = allMods.map(function(m) { return m.name; }).sort();
send({t: 'all_libs', count: sorted.length, libs: sorted});
