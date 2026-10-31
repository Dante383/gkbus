/*
 * gkbus J2534 helper
 *
 * Loads a J2534 PassThru library and makes the calls gkbus sends it. It lets a 64 bit
 * Python use a 32 bit J2534 DLL, which is all Tactrix ships for the OpenPort 2.0.
 * gkbus starts it, writes requests to its stdin and reads the responses from its stdout.
 * The protocol is described in gkbus/device/j2534/bridge.py.
 *
 * Built for Windows by build.sh. Also builds on Linux and macOS, where the tests use it.
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <fcntl.h>
#include <io.h>
#define PASSTHRU WINAPI
#define read_fd _read
#define write_fd _write
#define dup_fd _dup
#define dup2_fd _dup2
#else
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>
#define PASSTHRU
#define read_fd read
#define write_fd write
#define dup_fd dup
#define dup2_fd dup2
#endif

#define MAGIC 0x424A4B47u /* GKJB */
#define VERSION 1u

enum {
	OP_LOAD,
	OP_OPEN,
	OP_CLOSE,
	OP_CONNECT,
	OP_DISCONNECT,
	OP_READ_MSGS,
	OP_WRITE_MSGS,
	OP_START_MSG_FILTER,
	OP_STOP_MSG_FILTER,
	OP_SET_PROGRAMMING_VOLTAGE,
	OP_READ_VERSION,
	OP_GET_LAST_ERROR,
	OP_IOCTL,
};

/* what PassThruIoctl's input and output pointers point to */
enum { ARG_NONE, ARG_CONFIG_LIST, ARG_MSG, ARG_BYTES, ARG_ULONG };

#define STATUS_NOERROR 0x00
#define STATUS_ERR_FAILED 0x07

#define MSG_DATA_MAX 4128
#define MAX_MSGS 1024
#define MAX_ITEMS 65536
#define MAX_REQUEST (16u << 20)
#define TEXT_SIZE 256
#define MAX_DEVICES 16

typedef struct {
	unsigned long ProtocolID;
	unsigned long RxStatus;
	unsigned long TxFlags;
	unsigned long Timestamp;
	unsigned long DataSize;
	unsigned long ExtraDataIndex;
	unsigned char Data[MSG_DATA_MAX];
} PASSTHRU_MSG;

typedef struct {
	unsigned long Parameter;
	unsigned long Value;
} SCONFIG;

typedef struct {
	unsigned long NumOfParams;
	SCONFIG *ConfigPtr;
} SCONFIG_LIST;

typedef struct {
	unsigned long NumOfBytes;
	unsigned char *BytePtr;
} SBYTE_ARRAY;

static struct {
	long (PASSTHRU *Open)(void *, unsigned long *);
	long (PASSTHRU *Close)(unsigned long);
	long (PASSTHRU *Connect)(unsigned long, unsigned long, unsigned long, unsigned long,
		unsigned long *);
	long (PASSTHRU *Disconnect)(unsigned long);
	long (PASSTHRU *ReadMsgs)(unsigned long, PASSTHRU_MSG *, unsigned long *, unsigned long);
	long (PASSTHRU *WriteMsgs)(unsigned long, PASSTHRU_MSG *, unsigned long *, unsigned long);
	long (PASSTHRU *StartMsgFilter)(unsigned long, unsigned long, PASSTHRU_MSG *,
		PASSTHRU_MSG *, PASSTHRU_MSG *, unsigned long *);
	long (PASSTHRU *StopMsgFilter)(unsigned long, unsigned long);
	long (PASSTHRU *SetProgrammingVoltage)(unsigned long, unsigned long, unsigned long);
	long (PASSTHRU *ReadVersion)(unsigned long, char *, char *, char *);
	long (PASSTHRU *GetLastError)(char *);
	long (PASSTHRU *Ioctl)(unsigned long, unsigned long, void *, void *);
} pt;

#ifdef _WIN32
static HMODULE library;
#else
static void *library;
#endif

static int in_fd, out_fd;

/* devices opened and not closed yet, closed if gkbus goes away without closing them */
static unsigned long devices[MAX_DEVICES];
static int device_count;

/* the response being built */
static struct {
	unsigned char *data;
	size_t size, capacity;
} out;
static char text[TEXT_SIZE];

typedef struct {
	const unsigned char *p;
	size_t left;
	int bad;
} reader;

static void out_of_memory (void) {
	fputs("gkbus J2534 helper: out of memory\n", stderr);
	exit(1);
}

static void *allocate (size_t count, size_t size) {
	void *p = calloc(count ? count : 1, size);
	if (!p)
		out_of_memory();
	return p;
}

static void put_bytes (const void *data, size_t size) {
	if (out.size + size > out.capacity) {
		size_t capacity = out.capacity ? out.capacity : 4096;
		while (capacity < out.size + size)
			capacity *= 2;
		out.data = realloc(out.data, capacity);
		if (!out.data)
			out_of_memory();
		out.capacity = capacity;
	}
	if (size)
		memcpy(out.data + out.size, data, size);
	out.size += size;
}

static void encode_u32 (unsigned char *p, uint32_t value) {
	p[0] = value & 0xFF;
	p[1] = (value >> 8) & 0xFF;
	p[2] = (value >> 16) & 0xFF;
	p[3] = (value >> 24) & 0xFF;
}

static uint32_t decode_u32 (const unsigned char *p) {
	return p[0] | (p[1] << 8) | ((uint32_t) p[2] << 16) | ((uint32_t) p[3] << 24);
}

static void put_u32 (uint32_t value) {
	unsigned char p[4];
	encode_u32(p, value);
	put_bytes(p, 4);
}

static const unsigned char *take (reader *r, size_t size) {
	const unsigned char *p = r->p;
	if (r->bad || size > r->left) {
		r->bad = 1;
		return NULL;
	}
	r->p += size;
	r->left -= size;
	return p;
}

static unsigned long get_u32 (reader *r) {
	const unsigned char *p = take(r, 4);
	return p ? decode_u32(p) : 0;
}

static void get_msg (reader *r, PASSTHRU_MSG *msg) {
	const unsigned char *data;
	msg->ProtocolID = get_u32(r);
	msg->RxStatus = get_u32(r);
	msg->TxFlags = get_u32(r);
	msg->Timestamp = get_u32(r);
	msg->DataSize = get_u32(r);
	msg->ExtraDataIndex = get_u32(r);
	if (msg->DataSize > MSG_DATA_MAX) {
		r->bad = 1;
		return;
	}
	data = take(r, msg->DataSize);
	if (data)
		memcpy(msg->Data, data, msg->DataSize);
}

static void put_msg (const PASSTHRU_MSG *msg) {
	unsigned long size = msg->DataSize < MSG_DATA_MAX ? msg->DataSize : MSG_DATA_MAX;
	put_u32(msg->ProtocolID);
	put_u32(msg->RxStatus);
	put_u32(msg->TxFlags);
	put_u32(msg->Timestamp);
	put_u32(size);
	put_u32(msg->ExtraDataIndex);
	put_bytes(msg->Data, size);
}

static void put_text (const char *buffer) {
	size_t size = 0;
	while (size < TEXT_SIZE - 1 && buffer[size])
		size++;
	put_u32(size);
	put_bytes(buffer, size);
}

static void set_text (const char *message) {
	snprintf(text, sizeof text, "%s", message);
}

static int read_all (void *buffer, size_t size) {
	unsigned char *p = buffer;
	while (size) {
		int n = read_fd(in_fd, p, size > 65536 ? 65536 : (unsigned) size);
		if (n <= 0)
			return 0;
		p += n;
		size -= n;
	}
	return 1;
}

static int write_all (const void *buffer, size_t size) {
	const unsigned char *p = buffer;
	while (size) {
		int n = write_fd(out_fd, p, size > 65536 ? 65536 : (unsigned) size);
		if (n <= 0)
			return 0;
		p += n;
		size -= n;
	}
	return 1;
}

/* Keeps the pipes to gkbus to itself, so whatever the library prints can't get into them */
static void take_pipes (void) {
	in_fd = dup_fd(0);
	out_fd = dup_fd(1);
#ifdef _WIN32
	_setmode(in_fd, _O_BINARY);
	_setmode(out_fd, _O_BINARY);
	if (dup2_fd(2, 1) != 0) {
		int null_fd = _open("NUL", _O_WRONLY);
		if (null_fd >= 0)
			dup2_fd(null_fd, 1);
	}
	SetStdHandle(STD_OUTPUT_HANDLE, (HANDLE) _get_osfhandle(1));
	/* no "the program can't start" message boxes when a library is missing something */
	SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX);
#else
	if (dup2_fd(2, 1) < 0) {
		int null_fd = open("/dev/null", O_WRONLY);
		if (null_fd >= 0)
			dup2_fd(null_fd, 1);
	}
	signal(SIGPIPE, SIG_IGN);
#endif
}

static void *symbol (const char *name) {
#ifdef _WIN32
	return (void *) GetProcAddress(library, name);
#else
	return dlsym(library, name);
#endif
}

#define BIND(field, name) \
	if (!(*(void **) &pt.field = symbol(name))) \
		missing = name

static long load (reader *r) {
	unsigned long magic = get_u32(r), version = get_u32(r);
	size_t size = r->left;
	const unsigned char *path = take(r, size);
	const char *missing = NULL;
	char *name;

	if (r->bad)
		return STATUS_NOERROR;
	put_u32(MAGIC);
	put_u32(VERSION);
	if (magic != MAGIC || version != VERSION) {
		snprintf(text, sizeof text, "this is gkbus J2534 helper version %u, gkbus asked for %lu",
			VERSION, magic == MAGIC ? version : 0);
		return STATUS_ERR_FAILED;
	}
	if (library) {
		set_text("a library is already loaded");
		return STATUS_ERR_FAILED;
	}
	name = allocate(size + 1, 1);
	memcpy(name, path, size);
#ifdef _WIN32
	{
		int length = MultiByteToWideChar(CP_UTF8, 0, name, -1, NULL, 0);
		wchar_t *wide = allocate(length > 0 ? length : 1, sizeof *wide);
		MultiByteToWideChar(CP_UTF8, 0, name, -1, wide, length);
		/* its own directory first, for the DLLs it needs */
		library = LoadLibraryExW(wide, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
		free(wide);
		if (!library) {
			DWORD error = GetLastError();
			int n = snprintf(text, sizeof text, "LoadLibrary failed with error %lu: ",
				(unsigned long) error);
			if (n > 0 && n < (int) sizeof text)
				FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, NULL,
					error, 0, text + n, sizeof text - n, NULL);
		}
	}
#else
	library = dlopen(name, RTLD_NOW | RTLD_LOCAL);
	if (!library)
		snprintf(text, sizeof text, "%s", dlerror());
#endif
	free(name);
	if (!library)
		return STATUS_ERR_FAILED;

	BIND(Open, "PassThruOpen");
	BIND(Close, "PassThruClose");
	BIND(Connect, "PassThruConnect");
	BIND(Disconnect, "PassThruDisconnect");
	BIND(ReadMsgs, "PassThruReadMsgs");
	BIND(WriteMsgs, "PassThruWriteMsgs");
	BIND(StartMsgFilter, "PassThruStartMsgFilter");
	BIND(StopMsgFilter, "PassThruStopMsgFilter");
	BIND(SetProgrammingVoltage, "PassThruSetProgrammingVoltage");
	BIND(ReadVersion, "PassThruReadVersion");
	BIND(GetLastError, "PassThruGetLastError");
	BIND(Ioctl, "PassThruIoctl");
	if (missing) {
		snprintf(text, sizeof text, "not a J2534 library, it has no %s", missing);
		memset(&pt, 0, sizeof pt);
		return STATUS_ERR_FAILED;
	}
	return STATUS_NOERROR;
}

static void remember (unsigned long device_id) {
	if (device_count < MAX_DEVICES)
		devices[device_count++] = device_id;
}

static void forget (unsigned long device_id) {
	int i;
	for (i = 0; i < device_count; i++) {
		if (devices[i] == device_id) {
			devices[i] = devices[--device_count];
			return;
		}
	}
}

static long read_msgs (reader *r) {
	unsigned long channel = get_u32(r), count = get_u32(r), timeout = get_u32(r);
	unsigned long read, i;
	PASSTHRU_MSG *msgs;
	long status;

	if (r->bad)
		return STATUS_NOERROR;
	if (count > MAX_MSGS)
		count = MAX_MSGS;
	msgs = allocate(count, sizeof *msgs);
	read = count;
	status = pt.ReadMsgs(channel, msgs, &read, timeout);
	if (read > count)
		read = count;
	put_u32(read);
	for (i = 0; i < read; i++)
		put_msg(&msgs[i]);
	free(msgs);
	return status;
}

static long write_msgs (reader *r) {
	unsigned long channel = get_u32(r), timeout = get_u32(r), count = get_u32(r);
	unsigned long written, i;
	PASSTHRU_MSG *msgs;
	long status = STATUS_NOERROR;

	if (count > MAX_MSGS)
		r->bad = 1;
	if (r->bad)
		return status;
	msgs = allocate(count, sizeof *msgs);
	for (i = 0; i < count; i++)
		get_msg(r, &msgs[i]);
	if (!r->bad) {
		written = count;
		status = pt.WriteMsgs(channel, msgs, &written, timeout);
		put_u32(written);
	}
	free(msgs);
	return status;
}

static long start_msg_filter (reader *r) {
	unsigned long channel = get_u32(r), type = get_u32(r), flow_control = get_u32(r);
	unsigned long filter_id = 0;
	PASSTHRU_MSG *msgs = allocate(3, sizeof *msgs);
	long status = STATUS_NOERROR;

	get_msg(r, &msgs[0]);
	get_msg(r, &msgs[1]);
	if (flow_control)
		get_msg(r, &msgs[2]);
	if (!r->bad) {
		status = pt.StartMsgFilter(channel, type, &msgs[0], &msgs[1],
			flow_control ? &msgs[2] : NULL, &filter_id);
		put_u32(filter_id);
	}
	free(msgs);
	return status;
}

static long read_version (reader *r) {
	unsigned long device_id = get_u32(r);
	char firmware[TEXT_SIZE] = {0}, dll[TEXT_SIZE] = {0}, api[TEXT_SIZE] = {0};
	long status;

	if (r->bad)
		return STATUS_NOERROR;
	status = pt.ReadVersion(device_id, firmware, dll, api);
	put_text(firmware);
	put_text(dll);
	put_text(api);
	return status;
}

static long passthru_ioctl (reader *r) {
	unsigned long channel = get_u32(r), ioctl_id = get_u32(r);
	unsigned long in_kind = get_u32(r), out_kind, count = 0, capacity = 0, i;
	unsigned long in_value = 0, out_value = 0;
	PASSTHRU_MSG *msgs = allocate(2, sizeof *msgs);
	SCONFIG *configs = NULL;
	SCONFIG_LIST config_list = {0, NULL};
	SBYTE_ARRAY in_bytes = {0, NULL}, out_bytes = {0, NULL};
	void *in = NULL, *out_pointer = NULL;
	long status = STATUS_NOERROR;

	switch (in_kind) {
	case ARG_NONE:
		break;
	case ARG_CONFIG_LIST:
		count = get_u32(r);
		if (count > MAX_ITEMS) {
			r->bad = 1;
			break;
		}
		configs = allocate(count, sizeof *configs);
		for (i = 0; i < count; i++) {
			configs[i].Parameter = get_u32(r);
			configs[i].Value = get_u32(r);
		}
		config_list.NumOfParams = count;
		config_list.ConfigPtr = configs;
		in = &config_list;
		break;
	case ARG_MSG:
		get_msg(r, &msgs[0]);
		in = &msgs[0];
		break;
	case ARG_BYTES: {
		const unsigned char *data;
		count = get_u32(r);
		data = take(r, count);
		if (!data)
			break;
		in_bytes.NumOfBytes = count;
		in_bytes.BytePtr = allocate(count, 1);
		memcpy(in_bytes.BytePtr, data, count);
		in = &in_bytes;
		break;
	}
	case ARG_ULONG:
		in_value = get_u32(r);
		in = &in_value;
		break;
	default:
		r->bad = 1;
	}

	out_kind = get_u32(r);
	switch (out_kind) {
	case ARG_NONE:
		break;
	case ARG_MSG:
		out_pointer = &msgs[1];
		break;
	case ARG_BYTES:
		capacity = get_u32(r);
		if (capacity > MAX_REQUEST) {
			r->bad = 1;
			break;
		}
		out_bytes.NumOfBytes = capacity;
		out_bytes.BytePtr = allocate(capacity, 1);
		out_pointer = &out_bytes;
		break;
	case ARG_ULONG:
		out_pointer = &out_value;
		break;
	default:
		r->bad = 1;
	}

	if (!r->bad) {
		status = pt.Ioctl(channel, ioctl_id, in, out_pointer);
		if (in_kind == ARG_CONFIG_LIST) {
			put_u32(count);
			for (i = 0; i < count; i++) {
				put_u32(configs[i].Parameter);
				put_u32(configs[i].Value);
			}
		}
		if (out_kind == ARG_MSG) {
			put_msg(&msgs[1]);
		} else if (out_kind == ARG_BYTES) {
			unsigned long size = out_bytes.NumOfBytes < capacity ? out_bytes.NumOfBytes : capacity;
			put_u32(size);
			put_bytes(out_bytes.BytePtr, size);
		} else if (out_kind == ARG_ULONG) {
			put_u32(out_value);
		}
	}
	free(msgs);
	free(configs);
	free(in_bytes.BytePtr);
	free(out_bytes.BytePtr);
	return status;
}

static long handle (uint32_t op, reader *r) {
	unsigned long a, b, c, d, id = 0;
	long status;

	if (op != OP_LOAD && !pt.Ioctl) {
		set_text("no J2534 library is loaded");
		return STATUS_ERR_FAILED;
	}
	switch (op) {
	case OP_LOAD:
		return load(r);
	case OP_OPEN: {
		size_t size = r->left;
		const unsigned char *name = take(r, size);
		char *copy = NULL;
		if (size) {
			copy = allocate(size + 1, 1);
			memcpy(copy, name, size);
		}
		status = pt.Open(copy, &id);
		free(copy);
		put_u32(id);
		if (status == STATUS_NOERROR)
			remember(id);
		return status;
	}
	case OP_CLOSE:
		a = get_u32(r);
		if (r->bad)
			return STATUS_NOERROR;
		status = pt.Close(a);
		if (status == STATUS_NOERROR)
			forget(a);
		return status;
	case OP_CONNECT:
		a = get_u32(r);
		b = get_u32(r);
		c = get_u32(r);
		d = get_u32(r);
		if (r->bad)
			return STATUS_NOERROR;
		status = pt.Connect(a, b, c, d, &id);
		put_u32(id);
		return status;
	case OP_DISCONNECT:
		a = get_u32(r);
		return r->bad ? STATUS_NOERROR : pt.Disconnect(a);
	case OP_READ_MSGS:
		return read_msgs(r);
	case OP_WRITE_MSGS:
		return write_msgs(r);
	case OP_START_MSG_FILTER:
		return start_msg_filter(r);
	case OP_STOP_MSG_FILTER:
		a = get_u32(r);
		b = get_u32(r);
		return r->bad ? STATUS_NOERROR : pt.StopMsgFilter(a, b);
	case OP_SET_PROGRAMMING_VOLTAGE:
		a = get_u32(r);
		b = get_u32(r);
		c = get_u32(r);
		return r->bad ? STATUS_NOERROR : pt.SetProgrammingVoltage(a, b, c);
	case OP_READ_VERSION:
		return read_version(r);
	case OP_GET_LAST_ERROR: {
		char buffer[TEXT_SIZE] = {0};
		status = pt.GetLastError(buffer);
		buffer[TEXT_SIZE - 1] = 0;
		set_text(buffer);
		return status;
	}
	case OP_IOCTL:
		return passthru_ioctl(r);
	}
	snprintf(text, sizeof text, "unknown request %u", (unsigned) op);
	return STATUS_ERR_FAILED;
}

static int respond (long status) {
	unsigned char header[12];
	size_t text_size = strlen(text);
	encode_u32(header, (uint32_t) status);
	encode_u32(header + 4, out.size);
	encode_u32(header + 8, text_size);
	return write_all(header, sizeof header) && write_all(out.data, out.size)
		&& write_all(text, text_size);
}

int main (void) {
	unsigned char header[8], *request = NULL;
	size_t request_capacity = 0;

	take_pipes();
	for (;;) {
		uint32_t op, size;
		reader r;
		long status;

		if (!read_all(header, sizeof header))
			break;
		op = decode_u32(header);
		size = decode_u32(header + 4);
		if (size > MAX_REQUEST) {
			fputs("gkbus J2534 helper: request too long, out of step with gkbus\n", stderr);
			break;
		}
		if (size > request_capacity) {
			free(request);
			request = allocate(size, 1);
			request_capacity = size;
		}
		if (!read_all(request, size))
			break;

		r.p = request;
		r.left = size;
		r.bad = 0;
		out.size = 0;
		text[0] = 0;
		status = handle(op, &r);
		if (r.bad) {
			out.size = 0;
			set_text("malformed request");
			status = STATUS_ERR_FAILED;
		} else if (status != STATUS_NOERROR && !text[0] && pt.GetLastError) {
			/* the library's description of what went wrong, before anything else happens */
			char buffer[TEXT_SIZE] = {0};
			if (pt.GetLastError(buffer) == STATUS_NOERROR) {
				buffer[TEXT_SIZE - 1] = 0;
				set_text(buffer);
			}
		}
		if (!respond(status))
			break;
	}

	/* gkbus is gone, don't leave the adapter taken */
	while (device_count)
		pt.Close(devices[--device_count]);
	return 0;
}
